#!/usr/bin/env python3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.predictor import AerospaceHealthEngine  # noqa: E402
from llm.flight_surgeon import FlightSurgeonLLM, OLLAMA_MODEL  # noqa: E402
from schemas.contracts import TelemetryInput  # noqa: E402
from simulator.scenarios import SCENARIO_NAMES, generate_scenario  # noqa: E402

BASELINE_TELEMETRY = {
    "environment": "STATION",
    "hr": 68.0,
    "hrv_rmssd": 56.0,
    "spo2": 98.0,
    "sbp": 116.0,
    "dbp": 76.0,
    "temp_c": 36.7,
    "resp_rate": 14.0,
    "sleep_hours": 7.5,
}


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def check_ollama(surgeon: FlightSurgeonLLM) -> None:
    print_header("1. VERIFICACION DE OLLAMA")
    status = surgeon.ping()

    if status["reachable"] and status["model_available"]:
        print(f"Estado: OK. Ollama activo en localhost:11434 con el modelo '{OLLAMA_MODEL}' disponible.")
    elif status["reachable"]:
        print(f"Estado: ADVERTENCIA. Ollama esta activo pero el modelo '{OLLAMA_MODEL}' no esta descargado.")
        print(f"Comando para descargarlo: ollama pull {OLLAMA_MODEL}")
    else:
        print("Estado: ADVERTENCIA. Ollama no responde en localhost:11434.")
        print("Comando para iniciar el servicio: ollama serve")
        print(f"Comando para descargar el modelo: ollama pull {OLLAMA_MODEL}")
    print("El pipeline continua de todas formas: el fallback determinista cubre esta ausencia.")


def init_engine() -> AerospaceHealthEngine:
    print_header("2. INICIALIZACION DEL MOTOR DE PREDICCION")

    start = time.perf_counter()
    engine = AerospaceHealthEngine()
    load_ms = (time.perf_counter() - start) * 1000
    print(f"Motor cargado en {load_ms:.2f} ms. Clases soportadas: {', '.join(engine.class_labels)}")

    baseline = TelemetryInput(astronaut_id="AST-BASELINE", timestamp=time.time(), **BASELINE_TELEMETRY)
    start = time.perf_counter()
    engine.evaluate(baseline)
    inference_ms = (time.perf_counter() - start) * 1000
    print(f"Tiempo de inferencia de referencia (1 lectura): {inference_ms:.2f} ms.")

    return engine


def run_scenario(engine: AerospaceHealthEngine, surgeon: FlightSurgeonLLM, scenario_name: str) -> tuple[str, str]:
    print_header(f"ESCENARIO: {scenario_name.upper()}")

    astronaut_id = f"DEMO-{scenario_name.upper()}"
    packets = generate_scenario(scenario_name, astronaut_id=astronaut_id)

    final_diagnostic = None
    for index, packet in enumerate(packets, start=1):
        start = time.perf_counter()
        diagnostic = engine.evaluate(packet)
        inference_ms = (time.perf_counter() - start) * 1000
        print(
            f"  lectura {index}/3 ({inference_ms:6.2f} ms) -> "
            f"color={diagnostic.nasa_alert_color:<8} "
            f"prediccion={diagnostic.primary_prediction:<22} "
            f"probabilidad_principal={diagnostic.confidence_pct:5.1f}%"
        )
        final_diagnostic = diagnostic

    triggers = ", ".join(final_diagnostic.clinical_triggers) if final_diagnostic.clinical_triggers else "ninguno detectado"
    print(f"  triggers clinicos (lectura final): {triggers}")

    report = surgeon.generate_sbar_report(final_diagnostic)
    print(f"  reporte SBAR generado en {report.inference_time_sec * 1000:.2f} ms")
    print("  " + "-" * 74)
    for line in report.report_text.splitlines():
        print(f"  {line}")
    print("  " + "-" * 74)

    return final_diagnostic.nasa_alert_color, final_diagnostic.primary_prediction


def main() -> int:
    surgeon = FlightSurgeonLLM()
    check_ollama(surgeon)
    engine = init_engine()

    print_header("3-4. EJECUCION DE ESCENARIOS Y GENERACION DE REPORTES SBAR")
    summary: list[tuple[str, str, str]] = []
    for scenario_name in SCENARIO_NAMES:
        alert_color, primary_prediction = run_scenario(engine, surgeon, scenario_name)
        summary.append((scenario_name, alert_color, primary_prediction))

    print_header("RESUMEN FINAL")
    for scenario_name, alert_color, primary_prediction in summary:
        print(f"  {scenario_name:<15} color={alert_color:<8} prediccion={primary_prediction}")

    print()
    print("Verificacion completa. Pipeline local operativo de extremo a extremo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
