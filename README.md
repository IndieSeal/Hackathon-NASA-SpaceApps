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
| Reporte SBAR manual | `POST /report` |
| Guardado en Postgres | `GET /persistence/status`, `POST /persistence/start`, `POST /persistence/stop` |

Los umbrales clinicos viven solo en el backend: el frontend mapea cada disparador de `clinical_triggers` a un sistema del cuerpo y a su severidad.

## Capa de datos para varias interfaces (`scripts/telemetry.js`)

Cualquier pagina nueva carga `telemetry.js` y pide lo que necesita, sin repetir WebSocket ni `/history`:

```js
Telemetry.astronauts()             // ["AST-01", ...]
Telemetry.metric("AST-01", "spo2") // {label, unit, value, text, status: "ok|warn|crit", triggers, series}
Telemetry.all("AST-01")            // todas las metricas: hr, hrv, spo2, bp, temp, resp, shock, pulse, sleep
Telemetry.alert("AST-01")          // "VERDE" | "AMARILLO" | "ROJO"
Telemetry.latest("AST-01")         // DiagnosticOutput completo
Telemetry.on((id, d) => { ... })   // cada lectura nueva
Telemetry.profile("AST-01")        // {id, name, photo}; se edita en PROFILES o con setProfile()
```

`multi.html` + `scripts/multidashboard.js` son un ejemplo: un panel por astronauta con flechas para cambiar de metrica.

## Estado de simulacion por astronauta

El estado vive en el backend (`GET /stream/status`); el navegador no guarda nada.

```js
await Telemetry.isSimulating("AST-01")  // true si esta simulando, false si esta detenido
Telemetry.simulation("AST-01")          // {running, scenario} del ultimo sondeo (sincrono)
Telemetry.lastScenario("AST-01")        // escenario actual o el ultimo conocido
Telemetry.onSimulation(map => { ... })  // se llama cada 2 s y despues de iniciar o detener
```

La forma de la respuesta de `/stream/status` se interpreta en un solo lugar: `parseStreams()` en `scripts/telemetry.js`.
