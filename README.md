# Hackathon-NASA-SpaceApps

Dashboard de monitoreo de salud para astronautas (HTML, CSS, JS y Chart.js).

## Conexion con la API (Aerospace Health Monitoring Engine)

La URL base es el mismo origen de la pagina. Si el dashboard se abre desde otro servidor, agrega `?api=http://localhost:8000` (la API permite CORS).

| Uso | Endpoint |
|---|---|
| Telemetria y reportes en vivo | `WS /ws/telemetry` (mensajes `telemetry` y `sbar_report`) |
| Cargar graficas al abrir / respaldo si cae el WS | `GET /history` |
| Estado de Motor ML y Ollama | `GET /health` |
| Botones de escenario y detener | `POST /stream/start/{escenario}`, `POST /stream/stop` |
| Disparo unico (3 lecturas) | `POST /simulate/{escenario}` |
| Reporte SBAR manual | `POST /report` |
| Guardado en Postgres | `GET /persistence/status`, `POST /persistence/start`, `POST /persistence/stop` |

Los umbrales clinicos viven solo en el backend: el frontend mapea cada disparador de `clinical_triggers` a un sistema del cuerpo y a su severidad.
