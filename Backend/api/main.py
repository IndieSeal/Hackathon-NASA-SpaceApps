import asyncio
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db.connection import telemetry_store
from engine.predictor import AerospaceHealthEngine
from llm.flight_surgeon import OLLAMA_MODEL, FlightSurgeonLLM
from llm.pdf_report import REPORTS_DIR, write_pdf_report
from schemas.contracts import (
    ASTRONAUT_PROFILES,
    AstronautProfile,
    DiagnosticOutput,
    SBARReport,
    TelemetryInput,
)
from simulator.scenarios import LiveTelemetryStream, ScenarioName, generate_scenario

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"
REPORTES_HTML_PATH = STATIC_DIR / "reportes.html"

HISTORY_SIZE = 150
REPORT_HISTORY_SIZE = 200
STREAM_INTERVAL_SECONDS = 1.2
PERIODIC_REPORT_INTERVAL_SECONDS = 120


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for state in stream_states.values():
        await state.stop()
    await telemetry_store.disconnect()


app = FastAPI(
    title="Aerospace Health Monitoring Engine",
    description=(
        "Motor de prediccion biomedica y simulacion de telemetria para "
        "astronautas en mision espacial."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/reportes_pdf", StaticFiles(directory=str(REPORTS_DIR)), name="reportes_pdf")

engine = AerospaceHealthEngine()
flight_surgeon = FlightSurgeonLLM()

history: deque[DiagnosticOutput] = deque(maxlen=HISTORY_SIZE)
report_history: deque[SBARReport] = deque(maxlen=REPORT_HISTORY_SIZE)


def _record_report(sbar_report: SBARReport) -> SBARReport:
    pdf_filename = write_pdf_report(sbar_report)
    sbar_report = sbar_report.model_copy(update={"pdf_filename": pdf_filename})
    report_history.append(sbar_report)
    return sbar_report


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        stale: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self._connections.discard(connection)


connection_manager = ConnectionManager()


class OllamaHealth(BaseModel):
    model: str
    reachable: bool
    model_available: bool


class MLEngineHealth(BaseModel):
    ready: bool
    classes: list[str]


class HealthResponse(BaseModel):
    nasa_alert_color: Literal["VERDE", "AMARILLO", "ROJO"]
    ml_engine: MLEngineHealth
    ollama: OllamaHealth


class SimulationResult(BaseModel):
    scenario: ScenarioName
    readings: list[DiagnosticOutput]
    final_diagnostic: DiagnosticOutput
    report: SBARReport | None = None


class StreamStatus(BaseModel):
    status: Literal["started", "stopped"]
    scenario: ScenarioName | None = None
    astronaut_id: str


class PersistenceStatus(BaseModel):
    enabled: bool
    connected: bool
    saved_count: int
    last_error: str | None = None


class ColumnSchema(BaseModel):
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: str | None = None


class TableSchema(BaseModel):
    table_name: str
    columns: list[ColumnSchema]


class DatabaseSchemaResponse(BaseModel):
    connected: bool
    tables: list[TableSchema]
    error: str | None = None


class PersistenceState:
    def __init__(self) -> None:
        self.enabled = False
        self.saved_count = 0
        self.last_error: str | None = None

    def status(self) -> PersistenceStatus:
        return PersistenceStatus(
            enabled=self.enabled,
            connected=telemetry_store.is_connected,
            saved_count=self.saved_count,
            last_error=self.last_error,
        )


persistence_state = PersistenceState()


class StreamState:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.scenario: ScenarioName | None = None

    async def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        self.scenario = None

    def start(self, scenario_name: ScenarioName, astronaut_id: str) -> None:
        self.scenario = scenario_name
        self.task = asyncio.create_task(_stream_loop(scenario_name, astronaut_id))


stream_states: dict[str, StreamState] = {}


def _get_stream_state(astronaut_id: str) -> StreamState:
    state = stream_states.get(astronaut_id)
    if state is None:
        state = StreamState()
        stream_states[astronaut_id] = state
    return state


async def _broadcast_diagnostic(
    diagnostic: DiagnosticOutput,
    scenario: ScenarioName | None,
    source: str,
) -> None:
    history.append(diagnostic)
    await connection_manager.broadcast({"type": "telemetry", "data": diagnostic.model_dump(mode="json")})

    if persistence_state.enabled:
        try:
            await telemetry_store.insert_reading(diagnostic, scenario, source)
            persistence_state.saved_count += 1
            persistence_state.last_error = None
        except Exception as exc:
            persistence_state.last_error = str(exc)


async def _generate_and_broadcast_report(diagnostic: DiagnosticOutput) -> None:
    sbar_report = await asyncio.to_thread(flight_surgeon.generate_sbar_report, diagnostic)
    sbar_report = await asyncio.to_thread(_record_report, sbar_report)
    await connection_manager.broadcast({"type": "sbar_report", "data": sbar_report.model_dump(mode="json")})


async def _stream_loop(scenario_name: ScenarioName, astronaut_id: str) -> None:
    live_stream = LiveTelemetryStream(scenario_name, astronaut_id=astronaut_id)
    previous_alert_color: str | None = None
    elapsed_since_periodic_report = 0.0
    try:
        while True:
            telemetry = live_stream.next_reading()
            diagnostic = engine.evaluate(telemetry)
            await _broadcast_diagnostic(diagnostic, scenario=scenario_name, source="stream")

            if (
                diagnostic.nasa_alert_color in ("AMARILLO", "ROJO")
                and diagnostic.nasa_alert_color != previous_alert_color
            ):
                asyncio.create_task(_generate_and_broadcast_report(diagnostic))
                elapsed_since_periodic_report = 0.0
            previous_alert_color = diagnostic.nasa_alert_color

            elapsed_since_periodic_report += STREAM_INTERVAL_SECONDS
            if elapsed_since_periodic_report >= PERIODIC_REPORT_INTERVAL_SECONDS:
                elapsed_since_periodic_report = 0.0
                asyncio.create_task(_generate_and_broadcast_report(diagnostic))

            await asyncio.sleep(STREAM_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_HTML_PATH)


@app.get("/reportes.html", include_in_schema=False)
def reportes_page() -> FileResponse:
    return FileResponse(REPORTES_HTML_PATH)


@app.get("/history", response_model=list[DiagnosticOutput])
def get_history(astronaut_id: str | None = None) -> list[DiagnosticOutput]:
    readings = list(history)
    if astronaut_id:
        readings = [r for r in readings if r.astronaut_id == astronaut_id]
    return readings


@app.get("/reports", response_model=list[SBARReport])
def get_reports(astronaut_id: str | None = None) -> list[SBARReport]:
    reports = list(report_history)
    if astronaut_id:
        reports = [r for r in reports if r.astronaut_id == astronaut_id]
    return reports


@app.get("/astronauts", response_model=list[AstronautProfile])
def list_astronaut_profiles() -> list[AstronautProfile]:
    return list(ASTRONAUT_PROFILES.values())


@app.get("/astronauts/{astronaut_id}", response_model=AstronautProfile)
def get_astronaut_profile(astronaut_id: str) -> AstronautProfile:
    profile = ASTRONAUT_PROFILES.get(astronaut_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Astronauta no encontrado")
    return profile


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ollama_status = flight_surgeon.ping()
    ollama_health = OllamaHealth(model=OLLAMA_MODEL, **ollama_status)
    ml_health = MLEngineHealth(ready=engine.is_ready, classes=engine.class_labels)

    if not ml_health.ready:
        nasa_alert_color: Literal["VERDE", "AMARILLO", "ROJO"] = "ROJO"
    elif not (ollama_health.reachable and ollama_health.model_available):
        nasa_alert_color = "AMARILLO"
    else:
        nasa_alert_color = "VERDE"

    return HealthResponse(nasa_alert_color=nasa_alert_color, ml_engine=ml_health, ollama=ollama_health)


@app.post("/analyze", response_model=DiagnosticOutput)
def analyze(telemetry: TelemetryInput) -> DiagnosticOutput:
    return engine.evaluate(telemetry)


@app.post("/report", response_model=SBARReport)
def report(diagnostic: DiagnosticOutput) -> SBARReport:
    sbar_report = flight_surgeon.generate_sbar_report(diagnostic)
    return _record_report(sbar_report)


@app.post("/simulate/{scenario_name}", response_model=SimulationResult)
async def simulate(scenario_name: ScenarioName, astronaut_id: str = "AST-01") -> SimulationResult:
    packets = generate_scenario(scenario_name, astronaut_id=astronaut_id)

    readings: list[DiagnosticOutput] = []
    for packet in packets:
        diagnostic = engine.evaluate(packet)
        readings.append(diagnostic)
        await _broadcast_diagnostic(diagnostic, scenario=scenario_name, source="simulate")

    final_diagnostic = readings[-1]
    sbar_report = None
    if final_diagnostic.nasa_alert_color in ("AMARILLO", "ROJO"):
        sbar_report = await asyncio.to_thread(flight_surgeon.generate_sbar_report, final_diagnostic)
        sbar_report = await asyncio.to_thread(_record_report, sbar_report)
        await connection_manager.broadcast({"type": "sbar_report", "data": sbar_report.model_dump(mode="json")})

    return SimulationResult(
        scenario=scenario_name,
        readings=readings,
        final_diagnostic=final_diagnostic,
        report=sbar_report,
    )


@app.post("/stream/start/{scenario_name}", response_model=StreamStatus)
async def stream_start(scenario_name: ScenarioName, astronaut_id: str = "AST-01") -> StreamStatus:
    state = _get_stream_state(astronaut_id)
    await state.stop()
    state.start(scenario_name, astronaut_id)
    return StreamStatus(status="started", scenario=scenario_name, astronaut_id=astronaut_id)


@app.post("/stream/stop", response_model=StreamStatus)
async def stream_stop(astronaut_id: str = "AST-01") -> StreamStatus:
    state = _get_stream_state(astronaut_id)
    await state.stop()
    return StreamStatus(status="stopped", scenario=None, astronaut_id=astronaut_id)


@app.get("/stream/status", response_model=list[StreamStatus])
def stream_status() -> list[StreamStatus]:
    return [
        StreamStatus(
            status="started" if state.task is not None and not state.task.done() else "stopped",
            scenario=state.scenario,
            astronaut_id=astronaut_id,
        )
        for astronaut_id, state in stream_states.items()
    ]


@app.post("/persistence/start", response_model=PersistenceStatus)
async def persistence_start() -> PersistenceStatus:
    try:
        await telemetry_store.connect()
        persistence_state.enabled = True
        persistence_state.last_error = None
    except Exception as exc:
        persistence_state.enabled = False
        persistence_state.last_error = str(exc)
    return persistence_state.status()


@app.post("/persistence/stop", response_model=PersistenceStatus)
async def persistence_stop() -> PersistenceStatus:
    persistence_state.enabled = False
    return persistence_state.status()


@app.get("/persistence/status", response_model=PersistenceStatus)
async def persistence_status() -> PersistenceStatus:
    return persistence_state.status()


@app.get(
    "/persistence/schema",
    response_model=DatabaseSchemaResponse,
    summary="Esquema en vivo de la base de datos",
    description=(
        "Introspecciona Postgres en el momento de la llamada (information_schema) "
        "y devuelve tablas y columnas actuales. Util para confirmar en /docs que "
        "un cambio de esquema (p. ej. una columna nueva) ya quedo aplicado."
    ),
)
async def persistence_schema() -> DatabaseSchemaResponse:
    try:
        rows = await telemetry_store.fetch_schema()
    except Exception as exc:
        return DatabaseSchemaResponse(connected=False, tables=[], error=str(exc))

    tables_by_name: dict[str, list[ColumnSchema]] = {}
    for row in rows:
        tables_by_name.setdefault(row["table_name"], []).append(
            ColumnSchema(
                column_name=row["column_name"],
                data_type=row["data_type"],
                is_nullable=row["is_nullable"] == "YES",
                column_default=row["column_default"],
            )
        )

    return DatabaseSchemaResponse(
        connected=True,
        tables=[
            TableSchema(table_name=table_name, columns=columns)
            for table_name, columns in tables_by_name.items()
        ],
    )


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket) -> None:
    await connection_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
