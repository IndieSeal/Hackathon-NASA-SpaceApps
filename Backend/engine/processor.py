from collections import deque

from schemas.contracts import TelemetryInput

DEFAULT_WINDOW_SIZE = 30

# Linea base fisiologica de referencia en reposo (astronauta adulto sano),
# usada como punto de comparacion para los Z-Scores.
RESTING_BASELINE: dict[str, dict[str, float]] = {
    "hr": {"mean": 65.0, "std": 8.0},
    "hrv_rmssd": {"mean": 55.0, "std": 15.0},
    "spo2": {"mean": 98.0, "std": 1.0},
    "sbp": {"mean": 115.0, "std": 10.0},
    "dbp": {"mean": 75.0, "std": 8.0},
    "temp_c": {"mean": 36.8, "std": 0.3},
    "resp_rate": {"mean": 14.0, "std": 2.5},
    "sleep_hours": {"mean": 7.5, "std": 1.0},
}


class TelemetryWindowProcessor:
    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._buffers: dict[str, deque[TelemetryInput]] = {}

    def push(self, telemetry: TelemetryInput) -> dict[str, float]:
        buffer = self._buffer_for(telemetry.astronaut_id)
        buffer.append(telemetry)
        return self._compute_metrics(telemetry, buffer)

    def get_buffer(self, astronaut_id: str) -> list[TelemetryInput]:
        return list(self._buffers.get(astronaut_id, ()))

    def reset(self, astronaut_id: str | None = None) -> None:
        if astronaut_id is None:
            self._buffers.clear()
        else:
            self._buffers.pop(astronaut_id, None)

    def _buffer_for(self, astronaut_id: str) -> deque[TelemetryInput]:
        buffer = self._buffers.get(astronaut_id)
        if buffer is None:
            buffer = deque(maxlen=self._window_size)
            self._buffers[astronaut_id] = buffer
        return buffer

    def _compute_metrics(self, telemetry: TelemetryInput, buffer: deque[TelemetryInput]) -> dict[str, float]:
        oldest = buffer[0]
        elapsed_minutes = (telemetry.timestamp - oldest.timestamp) / 60.0

        metrics: dict[str, float] = {
            "shock_index": self._safe_ratio(telemetry.hr, telemetry.sbp),
            "pulse_pressure": telemetry.sbp - telemetry.dbp,
            "hr_slope": self._slope(telemetry.hr, oldest.hr, elapsed_minutes),
            "spo2_slope": self._slope(telemetry.spo2, oldest.spo2, elapsed_minutes),
        }
        metrics.update(self._z_scores(telemetry))
        return {key: round(value, 4) for key, value in metrics.items()}

    @staticmethod
    def _safe_ratio(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator else 0.0

    @staticmethod
    def _slope(current: float, oldest: float, elapsed_minutes: float) -> float:
        if elapsed_minutes <= 0:
            return 0.0
        return (current - oldest) / elapsed_minutes

    @staticmethod
    def _z_scores(telemetry: TelemetryInput) -> dict[str, float]:
        z_scores: dict[str, float] = {}
        for field_name, stats in RESTING_BASELINE.items():
            value = getattr(telemetry, field_name)
            std = stats["std"] or 1.0
            z_scores[f"{field_name}_zscore"] = (value - stats["mean"]) / std
        return z_scores
