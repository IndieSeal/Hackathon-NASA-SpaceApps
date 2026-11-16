import random
import time
from typing import Literal

from schemas.contracts import Environment, TelemetryInput, resolve_nombrec

ScenarioName = Literal["nominal", "ansiedad", "cardiovascular", "infeccion"]

INTERVAL_SECONDS = 90.0


def _build_sequence(
    astronaut_id: str,
    environment: Environment,
    start_timestamp: float,
    readings: list[dict[str, float]],
) -> list[TelemetryInput]:
    nombrec = resolve_nombrec(astronaut_id)
    return [
        TelemetryInput(
            astronaut_id=astronaut_id,
            nombrec=nombrec,
            environment=environment,
            timestamp=start_timestamp + index * INTERVAL_SECONDS,
            **reading,
        )
        for index, reading in enumerate(readings)
    ]


def _nominal(astronaut_id: str, start_timestamp: float) -> list[TelemetryInput]:
    readings = [
        {"hr": 68.0, "hrv_rmssd": 56.0, "spo2": 98.0, "sbp": 116.0, "dbp": 76.0, "temp_c": 36.7, "resp_rate": 14.0, "sleep_hours": 7.5},
        {"hr": 66.0, "hrv_rmssd": 58.0, "spo2": 98.0, "sbp": 114.0, "dbp": 75.0, "temp_c": 36.7, "resp_rate": 14.0, "sleep_hours": 7.5},
        {"hr": 67.0, "hrv_rmssd": 57.0, "spo2": 99.0, "sbp": 115.0, "dbp": 76.0, "temp_c": 36.8, "resp_rate": 15.0, "sleep_hours": 7.5},
    ]
    return _build_sequence(astronaut_id, "STATION", start_timestamp, readings)


def _ansiedad(astronaut_id: str, start_timestamp: float) -> list[TelemetryInput]:
    readings = [
        {"hr": 78.0, "hrv_rmssd": 48.0, "spo2": 97.0, "sbp": 118.0, "dbp": 78.0, "temp_c": 36.9, "resp_rate": 16.0, "sleep_hours": 6.5},
        {"hr": 102.0, "hrv_rmssd": 30.0, "spo2": 98.0, "sbp": 126.0, "dbp": 82.0, "temp_c": 37.0, "resp_rate": 23.0, "sleep_hours": 6.5},
        {"hr": 128.0, "hrv_rmssd": 16.0, "spo2": 99.0, "sbp": 134.0, "dbp": 86.0, "temp_c": 37.0, "resp_rate": 29.0, "sleep_hours": 6.5},
    ]
    return _build_sequence(astronaut_id, "SPACECRAFT", start_timestamp, readings)


def _cardiovascular(astronaut_id: str, start_timestamp: float) -> list[TelemetryInput]:
    readings = [
        {"hr": 88.0, "hrv_rmssd": 32.0, "spo2": 96.0, "sbp": 112.0, "dbp": 78.0, "temp_c": 36.6, "resp_rate": 18.0, "sleep_hours": 6.5},
        {"hr": 105.0, "hrv_rmssd": 22.0, "spo2": 92.0, "sbp": 100.0, "dbp": 75.0, "temp_c": 36.5, "resp_rate": 22.0, "sleep_hours": 6.5},
        {"hr": 128.0, "hrv_rmssd": 14.0, "spo2": 87.0, "sbp": 92.0, "dbp": 70.0, "temp_c": 36.4, "resp_rate": 26.0, "sleep_hours": 6.5},
    ]
    return _build_sequence(astronaut_id, "ROVER", start_timestamp, readings)


def _infeccion(astronaut_id: str, start_timestamp: float) -> list[TelemetryInput]:
    readings = [
        {"hr": 92.0, "hrv_rmssd": 35.0, "spo2": 96.0, "sbp": 110.0, "dbp": 72.0, "temp_c": 38.5, "resp_rate": 18.0, "sleep_hours": 6.0},
        {"hr": 98.0, "hrv_rmssd": 28.0, "spo2": 95.0, "sbp": 108.0, "dbp": 70.0, "temp_c": 38.7, "resp_rate": 19.0, "sleep_hours": 6.0},
        {"hr": 104.0, "hrv_rmssd": 22.0, "spo2": 94.0, "sbp": 106.0, "dbp": 68.0, "temp_c": 38.9, "resp_rate": 20.0, "sleep_hours": 6.0},
    ]
    return _build_sequence(astronaut_id, "LUNAR_BASE", start_timestamp, readings)


_SCENARIO_BUILDERS = {
    "nominal": _nominal,
    "ansiedad": _ansiedad,
    "cardiovascular": _cardiovascular,
    "infeccion": _infeccion,
}

SCENARIO_NAMES: tuple[str, ...] = tuple(_SCENARIO_BUILDERS)


def generate_scenario(
    scenario_name: ScenarioName,
    astronaut_id: str = "AST-01",
    start_timestamp: float | None = None,
) -> list[TelemetryInput]:
    builder = _SCENARIO_BUILDERS.get(scenario_name)
    if builder is None:
        raise ValueError(f"Escenario desconocido: {scenario_name}")
    return builder(astronaut_id, start_timestamp if start_timestamp is not None else time.time())


LIVE_SCENARIO_ENVIRONMENT: dict[ScenarioName, Environment] = {
    "nominal": "STATION",
    "ansiedad": "SPACECRAFT",
    "cardiovascular": "ROVER",
    "infeccion": "LUNAR_BASE",
}

# Perfil fisiologico objetivo por escenario para el flujo continuo en vivo:
# (media, desviacion por tick, minimo, maximo). Distinto de CLASS_PROFILES
# del motor de entrenamiento (engine/predictor.py): aqui la desviacion esta
# calibrada para producir variacion tick a tick suave y realista, no para
# generar un dataset de entrenamiento independiente.
LIVE_SCENARIO_PROFILES: dict[ScenarioName, dict[str, tuple[float, float, float, float]]] = {
    "nominal": {
        "hr": (68.0, 2.5, 58.0, 82.0),
        "hrv_rmssd": (56.0, 3.5, 42.0, 72.0),
        "spo2": (98.0, 0.3, 96.5, 99.5),
        "sbp": (115.0, 2.5, 106.0, 124.0),
        "dbp": (76.0, 2.0, 66.0, 84.0),
        "temp_c": (36.7, 0.08, 36.4, 37.0),
        "resp_rate": (14.0, 0.8, 11.0, 17.0),
        "sleep_hours": (7.5, 0.15, 7.0, 8.0),
    },
    "ansiedad": {
        "hr": (122.0, 5.0, 95.0, 160.0),
        "hrv_rmssd": (18.0, 3.0, 8.0, 32.0),
        "spo2": (97.0, 0.4, 94.0, 99.0),
        "sbp": (133.0, 4.0, 118.0, 155.0),
        "dbp": (86.0, 3.5, 72.0, 100.0),
        "temp_c": (37.0, 0.1, 36.6, 37.4),
        "resp_rate": (27.0, 1.8, 19.0, 34.0),
        "sleep_hours": (6.0, 0.2, 5.0, 7.0),
    },
    "cardiovascular": {
        "hr": (130.0, 7.0, 95.0, 190.0),
        "hrv_rmssd": (11.0, 2.5, 3.0, 24.0),
        "spo2": (88.0, 2.0, 78.0, 94.0),
        "sbp": (82.0, 5.0, 55.0, 110.0),
        "dbp": (52.0, 4.0, 35.0, 72.0),
        "temp_c": (36.4, 0.15, 35.7, 37.0),
        "resp_rate": (25.0, 2.2, 17.0, 32.0),
        "sleep_hours": (6.0, 0.2, 5.0, 7.0),
    },
    "infeccion": {
        "hr": (104.0, 4.0, 85.0, 135.0),
        "hrv_rmssd": (23.0, 3.0, 10.0, 40.0),
        "spo2": (94.0, 0.8, 88.0, 97.0),
        "sbp": (104.0, 4.0, 85.0, 120.0),
        "dbp": (66.0, 3.0, 50.0, 80.0),
        "temp_c": (39.0, 0.2, 37.8, 40.0),
        "resp_rate": (21.0, 1.5, 16.0, 29.0),
        "sleep_hours": (6.0, 0.2, 5.0, 7.0),
    },
}

LIVE_DRIFT_RATE = 0.22


class LiveTelemetryStream:
    """Generador con estado de lecturas continuas para un escenario.

    Cada llamada a `next_reading` aplica un paso de reversion a la media
    del perfil objetivo mas ruido gaussiano, para simular variacion
    fisiologica natural entre lecturas consecutivas en vez de muestreo
    independiente.
    """

    def __init__(
        self,
        scenario_name: ScenarioName,
        astronaut_id: str = "AST-01",
        seed: int | None = None,
    ) -> None:
        profile = LIVE_SCENARIO_PROFILES.get(scenario_name)
        if profile is None:
            raise ValueError(f"Escenario desconocido: {scenario_name}")

        self.scenario_name = scenario_name
        self.astronaut_id = astronaut_id
        self._environment = LIVE_SCENARIO_ENVIRONMENT[scenario_name]
        self._profile = profile
        self._rng = random.Random(seed)
        self._state: dict[str, float] = {
            field_name: mean for field_name, (mean, _std, _low, _high) in profile.items()
        }

    def next_reading(self) -> TelemetryInput:
        for field_name, (mean, std, low, high) in self._profile.items():
            current = self._state[field_name]
            drift = (mean - current) * LIVE_DRIFT_RATE
            noise = self._rng.gauss(0.0, std)
            self._state[field_name] = min(high, max(low, current + drift + noise))

        return TelemetryInput(
            astronaut_id=self.astronaut_id,
            nombrec=resolve_nombrec(self.astronaut_id),
            environment=self._environment,
            timestamp=time.time(),
            **self._state,
        )
