from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier

from engine.processor import RESTING_BASELINE, TelemetryWindowProcessor
from schemas.contracts import DiagnosticOutput, TelemetryInput

MODELS_DIR = Path(__file__).resolve().parent.parent / "models_store"
MODEL_PATH = MODELS_DIR / "aerospace_health_models.joblib"

RANDOM_STATE = 42
SAMPLES_PER_CLASS = 400

FEATURE_NAMES = (
    "hr",
    "hrv_rmssd",
    "spo2",
    "sbp",
    "dbp",
    "temp_c",
    "resp_rate",
    "sleep_hours",
    "shock_index",
    "pulse_pressure",
    "hr_slope",
    "spo2_slope",
    *(f"{field_name}_zscore" for field_name in RESTING_BASELINE),
)

# Perfiles fisiologicos sinteticos por clase: (media, desviacion, minimo, maximo).
# Los rangos estan calibrados sobre literatura clinica general de signos
# vitales y no corresponden a datos reales de ningun astronauta.
CLASS_PROFILES: dict[str, dict[str, tuple[float, float, float, float]]] = {
    "NOMINAL": {
        "hr": (65.0, 8.0, 50.0, 95.0),
        "hrv_rmssd": (55.0, 12.0, 30.0, 90.0),
        "spo2": (98.0, 0.7, 96.0, 100.0),
        "sbp": (115.0, 8.0, 100.0, 130.0),
        "dbp": (75.0, 6.0, 60.0, 85.0),
        "temp_c": (36.8, 0.2, 36.2, 37.2),
        "resp_rate": (14.0, 2.0, 10.0, 18.0),
        "sleep_hours": (7.5, 0.8, 6.0, 9.0),
        "hr_slope": (0.0, 0.5, -3.0, 3.0),
        "spo2_slope": (0.0, 0.15, -0.6, 0.6),
    },
    "ATAQUE_ANSIEDAD": {
        "hr": (118.0, 12.0, 95.0, 160.0),
        "hrv_rmssd": (20.0, 7.0, 8.0, 38.0),
        "spo2": (97.0, 1.0, 94.0, 99.0),
        "sbp": (132.0, 10.0, 115.0, 155.0),
        "dbp": (85.0, 8.0, 70.0, 100.0),
        "temp_c": (36.9, 0.2, 36.4, 37.4),
        "resp_rate": (25.0, 4.0, 18.0, 34.0),
        "sleep_hours": (6.0, 1.5, 3.0, 8.5),
        "hr_slope": (7.0, 3.0, 1.0, 15.0),
        "spo2_slope": (0.0, 0.3, -0.8, 0.8),
    },
    "EVENTO_CARDIOVASCULAR": {
        "hr": (128.0, 18.0, 90.0, 190.0),
        "hrv_rmssd": (12.0, 5.0, 3.0, 25.0),
        "spo2": (90.0, 4.0, 78.0, 96.0),
        "sbp": (85.0, 14.0, 55.0, 115.0),
        "dbp": (55.0, 10.0, 35.0, 75.0),
        "temp_c": (36.5, 0.4, 35.5, 37.3),
        "resp_rate": (23.0, 4.0, 16.0, 32.0),
        "sleep_hours": (6.0, 1.5, 3.0, 9.0),
        "hr_slope": (6.0, 4.0, -4.0, 16.0),
        "spo2_slope": (-1.6, 0.9, -4.0, 0.3),
    },
    "INFECCION_ENFERMEDAD": {
        "hr": (106.0, 10.0, 85.0, 135.0),
        "hrv_rmssd": (25.0, 8.0, 10.0, 45.0),
        "spo2": (95.0, 2.0, 88.0, 98.0),
        "sbp": (100.0, 10.0, 80.0, 120.0),
        "dbp": (65.0, 8.0, 50.0, 80.0),
        "temp_c": (38.6, 0.6, 37.6, 40.0),
        "resp_rate": (21.0, 3.0, 16.0, 30.0),
        "sleep_hours": (6.5, 1.5, 3.0, 9.0),
        "hr_slope": (2.0, 1.5, -2.0, 6.0),
        "spo2_slope": (-0.4, 0.3, -1.4, 0.3),
    },
    "FATIGA_CIRCADIANA": {
        "hr": (74.0, 9.0, 55.0, 100.0),
        "hrv_rmssd": (28.0, 9.0, 12.0, 48.0),
        "spo2": (97.0, 1.0, 94.0, 99.0),
        "sbp": (112.0, 10.0, 95.0, 135.0),
        "dbp": (74.0, 8.0, 58.0, 90.0),
        "temp_c": (36.6, 0.3, 36.0, 37.2),
        "resp_rate": (15.0, 2.0, 11.0, 20.0),
        "sleep_hours": (3.2, 1.0, 1.0, 5.0),
        "hr_slope": (0.5, 1.0, -2.0, 3.0),
        "spo2_slope": (0.0, 0.2, -0.6, 0.6),
    },
}

CRITICAL_TRIGGERS = frozenset(
    {
        "ARRITMIA_EXTREMA",
        "TAQUICARDIA_SEVERA",
        "HIPOXIA_CRITICA",
        "INDICE_DE_CHOQUE_CRITICO",
        "HIPOTENSION_SEVERA",
        "CRISIS_HIPERTENSIVA",
        "FIEBRE_ALTA",
        "HIPOTERMIA",
        "TAQUIPNEA_SEVERA",
        "BRADIPNEA_CRITICA",
        "DESATURACION_RAPIDA_DE_OXIGENO",
    }
)


def _sample_profile(
    rng: np.random.Generator,
    profile: dict[str, tuple[float, float, float, float]],
    n_samples: int,
) -> dict[str, np.ndarray]:
    samples: dict[str, np.ndarray] = {}
    for field_name, (mean, std, low, high) in profile.items():
        values = rng.normal(mean, std, n_samples)
        samples[field_name] = np.clip(values, low, high)
    return samples


def _build_feature_matrix(samples: dict[str, np.ndarray]) -> np.ndarray:
    hr = samples["hr"]
    sbp = samples["sbp"]
    dbp = samples["dbp"]
    shock_index = hr / sbp
    pulse_pressure = sbp - dbp

    columns = [
        samples["hr"],
        samples["hrv_rmssd"],
        samples["spo2"],
        samples["sbp"],
        samples["dbp"],
        samples["temp_c"],
        samples["resp_rate"],
        samples["sleep_hours"],
        shock_index,
        pulse_pressure,
        samples["hr_slope"],
        samples["spo2_slope"],
    ]
    for field_name, stats in RESTING_BASELINE.items():
        columns.append((samples[field_name] - stats["mean"]) / stats["std"])
    return np.column_stack(columns)


def _generate_training_data(
    rng: np.random.Generator, samples_per_class: int = SAMPLES_PER_CLASS
) -> tuple[np.ndarray, np.ndarray]:
    feature_blocks = []
    label_blocks = []
    for class_name, profile in CLASS_PROFILES.items():
        samples = _sample_profile(rng, profile, samples_per_class)
        feature_blocks.append(_build_feature_matrix(samples))
        label_blocks.append(np.full(samples_per_class, class_name))
    return np.vstack(feature_blocks), np.concatenate(label_blocks)


def _train_models() -> dict[str, object]:
    rng = np.random.default_rng(RANDOM_STATE)
    features, labels = _generate_training_data(rng)

    classifier = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        random_state=RANDOM_STATE,
        class_weight="balanced",
    )
    classifier.fit(features, labels)

    nominal_mask = labels == "NOMINAL"
    anomaly_detector = IsolationForest(
        n_estimators=200,
        contamination=0.03,
        random_state=RANDOM_STATE,
    )
    anomaly_detector.fit(features[nominal_mask])

    return {
        "classifier": classifier,
        "anomaly_detector": anomaly_detector,
        "feature_names": FEATURE_NAMES,
    }


class AerospaceHealthEngine:
    def __init__(
        self,
        window_processor: TelemetryWindowProcessor | None = None,
        models_path: Path | None = None,
    ) -> None:
        self._window_processor = window_processor or TelemetryWindowProcessor()
        self._models_path = models_path or MODEL_PATH
        self._classifier, self._anomaly_detector = self._load_or_train()

    def evaluate(self, telemetry: TelemetryInput) -> DiagnosticOutput:
        derived_metrics = self._window_processor.push(telemetry)
        features = self._feature_vector(telemetry, derived_metrics)

        probability_row = self._classifier.predict_proba(features)[0]
        probabilities = {
            label: round(float(probability), 4)
            for label, probability in zip(self._classifier.classes_, probability_row)
        }
        primary_prediction = max(probabilities, key=probabilities.get)
        confidence_pct = round(probabilities[primary_prediction] * 100.0, 2)

        unsupervised_anomaly = bool(self._anomaly_detector.predict(features)[0] == -1)
        clinical_triggers = self._extract_clinical_triggers(telemetry, derived_metrics)
        nasa_alert_color = self._assign_alert_color(
            primary_prediction, confidence_pct, unsupervised_anomaly, clinical_triggers
        )

        return DiagnosticOutput(
            astronaut_id=telemetry.astronaut_id,
            nasa_alert_color=nasa_alert_color,
            primary_prediction=primary_prediction,
            confidence_pct=confidence_pct,
            probabilities=probabilities,
            unsupervised_anomaly=unsupervised_anomaly,
            clinical_triggers=clinical_triggers,
            derived_metrics=derived_metrics,
            raw_telemetry=telemetry,
        )

    @property
    def is_ready(self) -> bool:
        return self._classifier is not None and self._anomaly_detector is not None

    @property
    def class_labels(self) -> list[str]:
        return list(self._classifier.classes_)

    def _load_or_train(self) -> tuple[RandomForestClassifier, IsolationForest]:
        if self._models_path.exists():
            bundle = joblib.load(self._models_path)
        else:
            bundle = _train_models()
            self._models_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(bundle, self._models_path)
        return bundle["classifier"], bundle["anomaly_detector"]

    @staticmethod
    def _feature_vector(telemetry: TelemetryInput, derived_metrics: dict[str, float]) -> np.ndarray:
        values = [
            telemetry.hr,
            telemetry.hrv_rmssd,
            telemetry.spo2,
            telemetry.sbp,
            telemetry.dbp,
            telemetry.temp_c,
            telemetry.resp_rate,
            telemetry.sleep_hours,
            derived_metrics["shock_index"],
            derived_metrics["pulse_pressure"],
            derived_metrics["hr_slope"],
            derived_metrics["spo2_slope"],
        ]
        values.extend(derived_metrics[f"{field_name}_zscore"] for field_name in RESTING_BASELINE)
        return np.asarray(values, dtype=float).reshape(1, -1)

    @staticmethod
    def _extract_clinical_triggers(telemetry: TelemetryInput, derived_metrics: dict[str, float]) -> list[str]:
        triggers: list[str] = []

        if telemetry.hr >= 150 or telemetry.hr <= 40:
            triggers.append("ARRITMIA_EXTREMA")
        elif telemetry.hr >= 120:
            triggers.append("TAQUICARDIA_SEVERA")
        elif telemetry.hr >= 100:
            triggers.append("TAQUICARDIA")
        elif telemetry.hr <= 50:
            triggers.append("BRADICARDIA")

        if telemetry.spo2 < 85:
            triggers.append("HIPOXIA_CRITICA")
        elif telemetry.spo2 < 92:
            triggers.append("HIPOXIA")

        if derived_metrics["shock_index"] >= 1.0:
            triggers.append("INDICE_DE_CHOQUE_CRITICO")
        elif derived_metrics["shock_index"] >= 0.9:
            triggers.append("INDICE_DE_CHOQUE_ELEVADO")

        if telemetry.sbp <= 80:
            triggers.append("HIPOTENSION_SEVERA")
        elif telemetry.sbp <= 90:
            triggers.append("HIPOTENSION")
        elif telemetry.sbp >= 160:
            triggers.append("CRISIS_HIPERTENSIVA")
        elif telemetry.sbp >= 140:
            triggers.append("HIPERTENSION")

        if derived_metrics["pulse_pressure"] <= 20:
            triggers.append("PRESION_DE_PULSO_ESTRECHA")
        elif derived_metrics["pulse_pressure"] >= 70:
            triggers.append("PRESION_DE_PULSO_AMPLIA")

        if telemetry.temp_c >= 39.5:
            triggers.append("FIEBRE_ALTA")
        elif telemetry.temp_c >= 38.0:
            triggers.append("FIEBRE")
        elif telemetry.temp_c <= 35.0:
            triggers.append("HIPOTERMIA")

        if telemetry.resp_rate >= 28:
            triggers.append("TAQUIPNEA_SEVERA")
        elif telemetry.resp_rate >= 20:
            triggers.append("TAQUIPNEA")
        elif telemetry.resp_rate <= 8:
            triggers.append("BRADIPNEA_CRITICA")
        elif telemetry.resp_rate <= 10:
            triggers.append("BRADIPNEA")

        if telemetry.sleep_hours < 4.0:
            triggers.append("DEFICIT_DE_SUENO_SEVERO")
        elif telemetry.sleep_hours < 6.0:
            triggers.append("DEFICIT_DE_SUENO")

        if derived_metrics["spo2_slope"] <= -1.5:
            triggers.append("DESATURACION_RAPIDA_DE_OXIGENO")

        if derived_metrics["hr_slope"] >= 8.0:
            triggers.append("TAQUICARDIA_DE_INICIO_RAPIDO")

        if telemetry.hrv_rmssd <= 15.0:
            triggers.append("VARIABILIDAD_CARDIACA_SUPRIMIDA")

        return triggers

    @staticmethod
    def _assign_alert_color(
        primary_prediction: str,
        confidence_pct: float,
        unsupervised_anomaly: bool,
        clinical_triggers: list[str],
    ) -> str:
        has_critical_trigger = any(trigger in CRITICAL_TRIGGERS for trigger in clinical_triggers)
        if has_critical_trigger or (primary_prediction == "EVENTO_CARDIOVASCULAR" and confidence_pct >= 50.0):
            return "ROJO"

        has_warning_signal = bool(clinical_triggers) or unsupervised_anomaly or primary_prediction != "NOMINAL"
        if has_warning_signal:
            return "AMARILLO"

        return "VERDE"
