import time

import requests

from schemas.contracts import DiagnosticOutput, SBARReport

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
REQUEST_TIMEOUT_SECONDS = (3.0, 30.0)
PING_TIMEOUT_SECONDS = 2.0

REQUIRED_SECTIONS = (
    "1. SITUACION",
    "2. ANALISIS FISIOLOGICO",
    "3. RIESGO ESPACIAL ASOCIADO",
    "4. PROTOCOLO DE ACCION INMEDIATA",
)

SYSTEM_PROMPT = (
    "Eres el cirujano de vuelo (Flight Surgeon) de una mision espacial. "
    "Redactas reportes clinicos en espanol siguiendo estrictamente el "
    "formato SBAR para control de mision. Recibes un diagnostico ya "
    "calculado por un sistema determinista; no debes recalcular, corregir "
    "ni inventar ninguna cifra, metrica o probabilidad: usa exclusivamente "
    "los valores entregados en el JSON de entrada. No uses emojis bajo "
    "ninguna circunstancia. No uses markdown: nada de asteriscos, negritas "
    "ni numerales adicionales. El reporte debe comenzar cada seccion "
    "exactamente con uno de estos cuatro encabezados literales, en texto "
    "plano, en este orden exacto y sin modificarlos:\n"
    "1. SITUACION\n"
    "2. ANALISIS FISIOLOGICO\n"
    "3. RIESGO ESPACIAL ASOCIADO\n"
    "4. PROTOCOLO DE ACCION INMEDIATA\n"
    "Ejemplo de formato esperado (reemplaza el contenido, no los "
    "encabezados):\n"
    "1. SITUACION\n"
    "<una o dos frases de situacion>\n\n"
    "2. ANALISIS FISIOLOGICO\n"
    "<lectura clinica de los signos vitales entregados>\n\n"
    "3. RIESGO ESPACIAL ASOCIADO\n"
    "<interpretacion del riesgo para la mision>\n\n"
    "4. PROTOCOLO DE ACCION INMEDIATA\n"
    "<accion recomendada>\n"
    "Se conciso, clinico y directo. No agregues secciones adicionales ni "
    "texto fuera de estas cuatro secciones."
)

PROTOCOLS_BY_COLOR = {
    "VERDE": (
        "Continuar actividades programadas. Mantener monitoreo de rutina "
        "sin intervencion adicional."
    ),
    "AMARILLO": (
        "Notificar a control de mision. Incrementar frecuencia de "
        "monitoreo y reevaluar al astronauta en el corto plazo."
    ),
    "ROJO": (
        "Activar protocolo de emergencia medica. Notificar de inmediato a "
        "control de mision y al cirujano de vuelo humano. Suspender "
        "actividades no esenciales del astronauta."
    ),
}


class FlightSurgeonLLM:
    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: tuple[float, float] = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._chat_url = f"{host}/api/chat"
        self._tags_url = f"{host}/api/tags"
        self._model = model
        self._timeout = timeout

    def ping(self) -> dict[str, bool]:
        try:
            response = requests.get(self._tags_url, timeout=PING_TIMEOUT_SECONDS)
            response.raise_for_status()
            model_names = [model.get("name", "") for model in response.json().get("models", [])]
        except (requests.exceptions.RequestException, ValueError):
            return {"reachable": False, "model_available": False}

        model_available = any(name == self._model or name.startswith(f"{self._model}:") for name in model_names)
        return {"reachable": True, "model_available": model_available}

    def generate_sbar_report(self, diagnostic: DiagnosticOutput) -> SBARReport:
        start = time.monotonic()
        report_text = self._generate_via_ollama(diagnostic)
        if report_text is None:
            report_text = self._fallback_report_text(diagnostic)
        inference_time_sec = round(time.monotonic() - start, 4)

        return SBARReport(
            astronaut_id=diagnostic.astronaut_id,
            alert_color=diagnostic.nasa_alert_color,
            diagnosis=diagnostic.primary_prediction,
            report_text=report_text,
            inference_time_sec=inference_time_sec,
            generated_at=time.time(),
        )

    def _generate_via_ollama(self, diagnostic: DiagnosticOutput) -> str | None:
        payload = {
            "model": self._model,
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0.15},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Redacta el reporte SBAR a partir de este diagnostico "
                        "clinico ya calculado. No inventes ni modifiques ningun "
                        "valor numerico, usa unicamente los datos de este "
                        f"JSON:\n{diagnostic.model_dump_json()}"
                    ),
                },
            ],
        }

        try:
            response = requests.post(self._chat_url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            content = response.json()["message"]["content"].strip()
        except (requests.exceptions.RequestException, KeyError, ValueError):
            return None

        if not content or not self._has_required_sections(content):
            return None
        return content

    @staticmethod
    def _has_required_sections(content: str) -> bool:
        return all(section in content for section in REQUIRED_SECTIONS)

    @staticmethod
    def _fallback_report_text(diagnostic: DiagnosticOutput) -> str:
        telemetry = diagnostic.raw_telemetry
        metrics = diagnostic.derived_metrics
        triggers = ", ".join(diagnostic.clinical_triggers) if diagnostic.clinical_triggers else "ninguno detectado"
        probabilities = ", ".join(
            f"{label}: {probability * 100:.1f} por ciento" for label, probability in diagnostic.probabilities.items()
        )
        anomaly_text = "si" if diagnostic.unsupervised_anomaly else "no"
        protocol = PROTOCOLS_BY_COLOR.get(
            diagnostic.nasa_alert_color, "Evaluar manualmente con el equipo medico de mision."
        )

        return (
            "1. SITUACION\n"
            f"Astronauta {diagnostic.astronaut_id} en entorno {telemetry.environment}. "
            f"Clasificacion de riesgo NASA: {diagnostic.nasa_alert_color}. "
            f"Prediccion principal: {diagnostic.primary_prediction} "
            f"(confianza {diagnostic.confidence_pct:.1f} por ciento).\n\n"
            "2. ANALISIS FISIOLOGICO\n"
            f"Frecuencia cardiaca: {telemetry.hr:.1f} bpm. HRV RMSSD: "
            f"{telemetry.hrv_rmssd:.1f} ms. SpO2: {telemetry.spo2:.1f} por "
            f"ciento. Presion arterial: {telemetry.sbp:.1f}/{telemetry.dbp:.1f} "
            f"mmHg. Temperatura corporal: {telemetry.temp_c:.1f} grados C. "
            f"Frecuencia respiratoria: {telemetry.resp_rate:.1f} rpm. Horas de "
            f"sueno en las ultimas 24 horas: {telemetry.sleep_hours:.1f}. "
            f"Indice de choque: {metrics.get('shock_index', 0.0):.3f}. Presion "
            f"de pulso: {metrics.get('pulse_pressure', 0.0):.1f} mmHg. Anomalia "
            f"no supervisada detectada: {anomaly_text}.\n\n"
            "3. RIESGO ESPACIAL ASOCIADO\n"
            f"Disparadores clinicos activos: {triggers}. Distribucion de "
            f"probabilidad por categoria: {probabilities}.\n\n"
            "4. PROTOCOLO DE ACCION INMEDIATA\n"
            f"{protocol}\n\n"
            "Nota: reporte generado por el protocolo determinista de "
            "respaldo porque el enlace con el modelo de lenguaje local no "
            "estuvo disponible en el momento de la generacion."
        )
