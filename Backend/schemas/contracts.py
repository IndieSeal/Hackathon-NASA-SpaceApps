from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Environment = Literal["SPACECRAFT", "STATION", "ROVER", "LUNAR_BASE"]
NasaAlertColor = Literal["VERDE", "AMARILLO", "ROJO"]
PrimaryPrediction = Literal[
    "NOMINAL",
    "ATAQUE_ANSIEDAD",
    "EVENTO_CARDIOVASCULAR",
    "INFECCION_ENFERMEDAD",
    "FATIGA_CIRCADIANA",
]


class PersonalInfo(BaseModel):
    nacimiento: str
    tipo_sangre: str
    nacionalidad: str


class AstronautProfile(BaseModel):
    astronaut_id: str
    nombrec: str
    puesto: str
    rango: str
    personales: PersonalInfo


ASTRONAUT_PROFILES: dict[str, AstronautProfile] = {
    "AST-01": AstronautProfile(
        astronaut_id="AST-01",
        nombrec="Mario Gonzales Castaleda",
        puesto="Especialista de Mision",
        rango="Comandante",
        personales=PersonalInfo(
            nacimiento="1988-04-12",
            tipo_sangre="O+",
            nacionalidad="Mexicana",
        ),
    ),
    "AST-02": AstronautProfile(
        astronaut_id="AST-02",
        nombrec="Elena Marquez Rivas",
        puesto="Piloto de Mision",
        rango="Teniente Coronel",
        personales=PersonalInfo(
            nacimiento="1990-09-23",
            tipo_sangre="A-",
            nacionalidad="Argentina",
        ),
    ),
    "AST-03": AstronautProfile(
        astronaut_id="AST-03",
        nombrec="Kwame Asante Boateng",
        puesto="Ingeniero de Vuelo",
        rango="Capitan",
        personales=PersonalInfo(
            nacimiento="1985-01-07",
            tipo_sangre="B+",
            nacionalidad="Ghanesa",
        ),
    ),
    "AST-04": AstronautProfile(
        astronaut_id="AST-04",
        nombrec="Yuki Tanaka Sato",
        puesto="Medico de Mision",
        rango="Mayor",
        personales=PersonalInfo(
            nacimiento="1992-06-30",
            tipo_sangre="AB+",
            nacionalidad="Japonesa",
        ),
    ),
}

ASTRONAUT_IDS: tuple[str, ...] = tuple(ASTRONAUT_PROFILES)


def resolve_nombrec(astronaut_id: str) -> str:
    profile = ASTRONAUT_PROFILES.get(astronaut_id)
    return profile.nombrec if profile is not None else astronaut_id


class TelemetryInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "astronaut_id": "AST-01",
                "nombrec": "Mario Gonzales Castaleda",
                "environment": "STATION",
                "timestamp": 1731600000.0,
                "hr": 78.0,
                "hrv_rmssd": 42.5,
                "spo2": 98.0,
                "sbp": 118.0,
                "dbp": 76.0,
                "temp_c": 36.8,
                "resp_rate": 16.0,
                "sleep_hours": 6.5,
            }
        },
    )

    astronaut_id: str = Field(default="AST-01", description="Identificador del astronauta")
    nombrec: str = Field(
        default="",
        description="Nombre completo del astronauta, solo para despliegue en el frontend",
    )
    environment: Environment = Field(description="Entorno operativo de la telemetria")
    timestamp: float = Field(description="Marca de tiempo UNIX de la lectura")
    hr: float = Field(description="Frecuencia cardiaca en bpm")
    hrv_rmssd: float = Field(description="Variabilidad cardiaca RMSSD en ms")
    spo2: float = Field(description="Saturacion de oxigeno en porcentaje")
    sbp: float = Field(description="Presion arterial sistolica en mmHg")
    dbp: float = Field(description="Presion arterial diastolica en mmHg")
    temp_c: float = Field(description="Temperatura corporal en grados Celsius")
    resp_rate: float = Field(description="Frecuencia respiratoria en rpm")
    sleep_hours: float = Field(description="Horas de sueno en las ultimas 24 horas")


class DiagnosticOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "astronaut_id": "AST-01",
                "nasa_alert_color": "AMARILLO",
                "primary_prediction": "FATIGA_CIRCADIANA",
                "confidence_pct": 82.3,
                "probabilities": {
                    "NOMINAL": 0.10,
                    "ATAQUE_ANSIEDAD": 0.03,
                    "EVENTO_CARDIOVASCULAR": 0.02,
                    "INFECCION_ENFERMEDAD": 0.02,
                    "FATIGA_CIRCADIANA": 0.83,
                },
                "unsupervised_anomaly": False,
                "clinical_triggers": ["SLEEP_DEFICIT_24H", "HRV_BELOW_BASELINE"],
                "derived_metrics": {
                    "shock_index": 0.66,
                    "pulse_pressure": 42.0,
                    "hr_slope": 1.2,
                    "spo2_slope": -0.1,
                },
                "raw_telemetry": {
                    "astronaut_id": "AST-01",
                    "nombrec": "Mario Gonzales Castaleda",
                    "environment": "STATION",
                    "timestamp": 1731600000.0,
                    "hr": 78.0,
                    "hrv_rmssd": 42.5,
                    "spo2": 98.0,
                    "sbp": 118.0,
                    "dbp": 76.0,
                    "temp_c": 36.8,
                    "resp_rate": 16.0,
                    "sleep_hours": 6.5,
                },
            }
        },
    )

    astronaut_id: str = Field(description="Identificador del astronauta")
    nasa_alert_color: NasaAlertColor = Field(description="Codigo de alerta NASA")
    primary_prediction: PrimaryPrediction = Field(description="Clase clinica principal predicha")
    confidence_pct: float = Field(description="Confianza de la prediccion principal en porcentaje")
    probabilities: dict[str, float] = Field(description="Distribucion de probabilidad por clase")
    unsupervised_anomaly: bool = Field(description="Indicador de anomalia detectada por modelo no supervisado")
    clinical_triggers: list[str] = Field(description="Reglas clinicas deterministas activadas")
    derived_metrics: dict[str, float] = Field(
        description=(
            "Metricas derivadas del motor clinico, incluyendo shock_index, "
            "pulse_pressure, hr_slope y spo2_slope"
        )
    )
    raw_telemetry: TelemetryInput = Field(description="Telemetria de entrada que origino el diagnostico")


class SBARReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "astronaut_id": "AST-01",
                "alert_color": "AMARILLO",
                "diagnosis": "FATIGA_CIRCADIANA",
                "report_text": (
                    "S: Astronauta AST-01 presenta signos de fatiga circadiana. "
                    "B: Horas de sueno por debajo del umbral en las ultimas 24 horas. "
                    "A: HRV reducida respecto a la linea base, resto de signos vitales "
                    "dentro de rango nominal. "
                    "R: Monitoreo continuo y reprogramacion de periodo de descanso."
                ),
                "inference_time_sec": 1.42,
                "generated_at": 1731600005.0,
                "pdf_filename": "SBAR_AST-01_1731600005.pdf",
            }
        },
    )

    astronaut_id: str = Field(description="Identificador del astronauta")
    alert_color: str = Field(description="Codigo de alerta NASA del reporte")
    diagnosis: str = Field(description="Diagnostico principal referenciado en el reporte")
    report_text: str = Field(description="Reporte clinico en espanol en formato SBAR")
    inference_time_sec: float = Field(description="Tiempo de inferencia del LLM en segundos")
    generated_at: float = Field(description="Marca de tiempo UNIX de generacion del reporte")
    pdf_filename: str | None = Field(
        default=None, description="Nombre del archivo PDF del reporte en /reportes_pdf"
    )
