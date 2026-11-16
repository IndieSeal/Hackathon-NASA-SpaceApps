# CLAUDE.md — Módulo IA / Predicción Biomédica / Simulación de Telemetría

Contexto: submódulo del proyecto para el NASA Space Apps Challenge 2026,
desafío "Create Health Monitoring Software for Astronauts on Space Missions".

## Stack

- Python 3.11+
- FastAPI (REST + WebSockets)
- Scikit-Learn / NumPy (modelos y cálculo numérico)
- Ollama local, modelo `llama3.2`, servido en `http://localhost:11434`

## Arquitectura estricta

- Todos los cálculos clínicos (Índice de Choque, Presión de Pulso, Z-Scores)
  y la clasificación de riesgo se calculan 100% en Python determinista
  (`engine/`). Nunca delegar estos cálculos al LLM.
- `llama3.2` solo recibe el JSON ya diagnosticado (resultado de `engine/`)
  y su única función es redactar reportes clínicos en español en formato
  SBAR (Situación, Background, Assessment, Recommendation). El LLM no
  decide clasificaciones de riesgo ni genera valores numéricos nuevos.

## Código de colores NASA

Toda respuesta de la API, reporte o clasificación de riesgo debe usar
exclusivamente estas tres categorías: `VERDE`, `AMARILLO`, `ROJO`.

## Prohibiciones

- Prohibido usar emojis en: logs, respuestas de API, reportes clínicos
  generados y comentarios de código.
