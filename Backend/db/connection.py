import json
import os

import asyncpg
from dotenv import load_dotenv

from schemas.contracts import DiagnosticOutput

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "aerospace_health")
DB_USER = os.getenv("POSTGRES_USER", "aerospace")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "aerospace_dev_only")
DB_CONNECT_TIMEOUT_SECONDS = 5.0

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS telemetry_readings (
    id BIGSERIAL PRIMARY KEY,
    astronaut_id TEXT NOT NULL,
    nombrec TEXT,
    scenario TEXT,
    source TEXT NOT NULL,
    nasa_alert_color TEXT NOT NULL,
    primary_prediction TEXT NOT NULL,
    confidence_pct DOUBLE PRECISION NOT NULL,
    unsupervised_anomaly BOOLEAN NOT NULL,
    clinical_triggers JSONB NOT NULL,
    probabilities JSONB NOT NULL,
    derived_metrics JSONB NOT NULL,
    raw_telemetry JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE telemetry_readings ADD COLUMN IF NOT EXISTS nombrec TEXT;
CREATE INDEX IF NOT EXISTS idx_telemetry_readings_recorded_at ON telemetry_readings (recorded_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_readings_astronaut_id ON telemetry_readings (astronaut_id);
"""

INSERT_SQL = """
INSERT INTO telemetry_readings (
    astronaut_id, nombrec, scenario, source, nasa_alert_color, primary_prediction,
    confidence_pct, unsupervised_anomaly, clinical_triggers, probabilities,
    derived_metrics, raw_telemetry
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb)
"""

SCHEMA_INTROSPECTION_SQL = """
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position
"""


class TelemetryStore:
    """Persistencia opcional de lecturas de telemetria en Postgres.

    La conexion se establece de forma perezosa (solo cuando se activa el
    guardado desde el dashboard) para que el servidor funcione sin Postgres
    disponible mientras la persistencia este desactivada.
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=1,
            max_size=5,
            timeout=DB_CONNECT_TIMEOUT_SECONDS,
        )
        try:
            async with pool.acquire() as connection:
                await connection.execute(SCHEMA_SQL)
        except Exception:
            await pool.close()
            raise
        self._pool = pool

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def insert_reading(
        self,
        diagnostic: DiagnosticOutput,
        scenario: str | None,
        source: str,
    ) -> None:
        if self._pool is None:
            raise RuntimeError("TelemetryStore no esta conectado")
        await self._pool.execute(
            INSERT_SQL,
            diagnostic.astronaut_id,
            diagnostic.raw_telemetry.nombrec,
            scenario,
            source,
            diagnostic.nasa_alert_color,
            diagnostic.primary_prediction,
            diagnostic.confidence_pct,
            diagnostic.unsupervised_anomaly,
            json.dumps(diagnostic.clinical_triggers),
            json.dumps(diagnostic.probabilities),
            json.dumps(diagnostic.derived_metrics),
            diagnostic.raw_telemetry.model_dump_json(),
        )

    async def fetch_schema(self) -> list[asyncpg.Record]:
        """Introspecciona en vivo las tablas y columnas actuales de Postgres."""
        if self._pool is None:
            await self.connect()
        async with self._pool.acquire() as connection:
            return await connection.fetch(SCHEMA_INTROSPECTION_SQL)


telemetry_store = TelemetryStore()
