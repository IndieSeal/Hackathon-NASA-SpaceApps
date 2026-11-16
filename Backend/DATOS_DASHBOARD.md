# Datos técnicos del dashboard — Aerospace Health Monitoring

Este documento describe, campo por campo, qué datos se muestran en `static/index.html`,
de dónde salen, cómo se calculan y qué representan clínicamente. Sirve como referencia
técnica del contrato de datos entre `engine/`, `api/main.py` y el frontend.

## 1. Flujo de datos de extremo a extremo

```
LiveTelemetryStream (simulator/scenarios.py)
        |  genera TelemetryInput cada 1.2s (paseo aleatorio con reversion a la media)
        v
AerospaceHealthEngine.evaluate() (engine/predictor.py)
        |  calcula metricas derivadas + clasifica + detecta anomalias + evalua reglas clinicas
        v
DiagnosticOutput
        |  se agrega al historial en memoria (ultimas 30 lecturas) y se transmite por WS
        |  si esta activo el boton "Guardado en BD", tambien se inserta en Postgres
        v
WS /ws/telemetry  ->  {"type": "telemetry", "data": DiagnosticOutput}
        |
        |  si nasa_alert_color pasa a AMARILLO/ROJO (transicion)
        v
FlightSurgeonLLM.generate_sbar_report() (llm/flight_surgeon.py, modelo llama3.2 via Ollama)
        |  redacta el texto SBAR a partir del DiagnosticOutput ya calculado (no inventa cifras)
        v
WS /ws/telemetry  ->  {"type": "sbar_report", "data": SBARReport}
```

Todo el cálculo clínico (índices, z-scores, clasificación de riesgo, color de alerta) ocurre
100% en Python determinista dentro de `engine/`. El LLM (`llama3.2`) solo redacta texto en
español a partir del JSON ya diagnosticado; nunca genera ni corrige valores numéricos.

## 2. Telemetría cruda (`TelemetryInput`)

Son los 8 signos vitales que entran al motor. En el modo simulado los genera
`LiveTelemetryStream`; en producción vendrían de sensores reales.

| Campo | Unidad | Descripción | Línea base en reposo (`RESTING_BASELINE`) |
|---|---|---|---|
| `hr` | bpm | Frecuencia cardíaca | media 65, desv. 8 |
| `hrv_rmssd` | ms | Variabilidad de frecuencia cardíaca (RMSSD) | media 55, desv. 15 |
| `spo2` | % | Saturación de oxígeno | media 98, desv. 1 |
| `sbp` | mmHg | Presión arterial sistólica | media 115, desv. 10 |
| `dbp` | mmHg | Presión arterial diastólica | media 75, desv. 8 |
| `temp_c` | °C | Temperatura corporal | media 36.8, desv. 0.3 |
| `resp_rate` | rpm | Frecuencia respiratoria | media 14, desv. 2.5 |
| `sleep_hours` | h | Horas de sueño en las últimas 24h | media 7.5, desv. 1.0 |

Además: `astronaut_id`, `environment` (`SPACECRAFT` / `STATION` / `ROVER` / `LUNAR_BASE`) y
`timestamp` (UNIX). La línea base se usa únicamente para calcular los z-scores internos del
clasificador; no se muestra directamente en el dashboard.

## 3. Métricas derivadas (`TelemetryWindowProcessor`, `engine/processor.py`)

Se calculan sobre una ventana deslizante de hasta 30 lecturas **por astronauta**, mantenida en
memoria del proceso del motor (independiente del historial del dashboard y de Postgres).

| Métrica | Fórmula | Mostrada en |
|---|---|---|
| `shock_index` | `hr / sbp` | Tarjeta KPI "Índice de Choque" |
| `pulse_pressure` | `sbp - dbp` | Tarjeta KPI "Presión de Pulso" |
| `hr_slope` | `(hr_actual - hr_más_antiguo_en_ventana) / minutos_transcurridos` | No se grafica directo; alimenta el disparador `TAQUICARDIA_DE_INICIO_RAPIDO` |
| `spo2_slope` | ídem para `spo2` | No se grafica directo; alimenta el disparador `DESATURACION_RAPIDA_DE_OXIGENO` |
| `{campo}_zscore` (8 campos) | `(valor - media_basal) / desviación_basal` | Uso interno como features del modelo ML, no se muestra |

## 4. Salida diagnóstica (`DiagnosticOutput`)

Es el objeto central que viaja por WS como `data` del mensaje `telemetry` y el que alimenta
todo el dashboard.

| Campo | Tipo | Origen | Uso en el dashboard |
|---|---|---|---|
| `astronaut_id` | string | input | Banner de triaje |
| `nasa_alert_color` | `VERDE` \| `AMARILLO` \| `ROJO` | regla determinista (sección 6) | Color del banner, borde de las tarjetas, color del dataset dominante en la gráfica de probabilidades |
| `primary_prediction` | una de 5 clases (sección 4.1) | `RandomForestClassifier` (200 árboles, entrenado sobre perfiles sintéticos) | Banner, resalta la barra correspondiente en la gráfica de probabilidades |
| `confidence_pct` | float % | `max(probabilities) * 100` | Banner ("confianza del modelo") |
| `probabilities` | dict clase→fracción (0-1) | `predict_proba` del clasificador | Gráfica de barras horizontales (se multiplica x100 en el frontend) |
| `unsupervised_anomaly` | bool | `IsolationForest` entrenado solo con el perfil `NOMINAL` (contaminación 3%) | Badge "ISOLATION FOREST: ANOMALIA DETECTADA / SIN ANOMALIA" en el banner |
| `clinical_triggers` | lista de strings | reglas deterministas sobre umbrales clínicos (sección 5) | Panel "Hallazgos Clínicos" y resaltado rojo/amarillo de las tarjetas KPI |
| `derived_metrics` | dict | sección 3 | Tarjetas "Índice de Choque" y "Presión de Pulso" |
| `raw_telemetry` | `TelemetryInput` | input original | Resto de tarjetas KPI y las 2 gráficas de líneas |

### 4.1 Clases de `primary_prediction`

`NOMINAL`, `ATAQUE_ANSIEDAD`, `EVENTO_CARDIOVASCULAR`, `INFECCION_ENFERMEDAD`,
`FATIGA_CIRCADIANA`. Las 5 aparecen siempre en la gráfica de probabilidades, pero
`FATIGA_CIRCADIANA` no tiene un botón de escenario propio en la barra de control (solo existe
como clase entrenada); puede aparecer con probabilidad no nula si la telemetría se acerca a ese
perfil, pero el simulador en vivo no la dispara deliberadamente.

## 5. Catálogo de disparadores clínicos (`clinical_triggers`)

Reglas evaluadas en `AerospaceHealthEngine._extract_clinical_triggers`. Son mutuamente
excluyentes dentro de cada signo vital (se evalúan como `if/elif`).

| Disparador | Condición | Severidad visual (frontend) |
|---|---|---|
| `ARRITMIA_EXTREMA` | `hr >= 150` o `hr <= 40` | crítico (rojo) |
| `TAQUICARDIA_SEVERA` | `hr >= 120` | crítico (rojo) |
| `TAQUICARDIA` | `hr >= 100` | advertencia (amarillo) |
| `BRADICARDIA` | `hr <= 50` | advertencia (amarillo) |
| `TAQUICARDIA_DE_INICIO_RAPIDO` | `hr_slope >= 8.0` bpm/min | advertencia (amarillo) |
| `HIPOXIA_CRITICA` | `spo2 < 85` | crítico (rojo) |
| `HIPOXIA` | `spo2 < 92` | advertencia (amarillo) |
| `DESATURACION_RAPIDA_DE_OXIGENO` | `spo2_slope <= -1.5` %/min | crítico (rojo) |
| `INDICE_DE_CHOQUE_CRITICO` | `shock_index >= 1.0` | crítico (rojo) |
| `INDICE_DE_CHOQUE_ELEVADO` | `shock_index >= 0.9` | advertencia (amarillo) |
| `HIPOTENSION_SEVERA` | `sbp <= 80` | crítico (rojo) |
| `HIPOTENSION` | `sbp <= 90` | advertencia (amarillo) |
| `CRISIS_HIPERTENSIVA` | `sbp >= 160` | crítico (rojo) |
| `HIPERTENSION` | `sbp >= 140` | advertencia (amarillo) |
| `PRESION_DE_PULSO_ESTRECHA` | `pulse_pressure <= 20` | advertencia (amarillo) |
| `PRESION_DE_PULSO_AMPLIA` | `pulse_pressure >= 70` | advertencia (amarillo) |
| `FIEBRE_ALTA` | `temp_c >= 39.5` | crítico (rojo) |
| `FIEBRE` | `temp_c >= 38.0` | advertencia (amarillo) |
| `HIPOTERMIA` | `temp_c <= 35.0` | crítico (rojo) |
| `TAQUIPNEA_SEVERA` | `resp_rate >= 28` | crítico (rojo) |
| `TAQUIPNEA` | `resp_rate >= 20` | advertencia (amarillo) |
| `BRADIPNEA_CRITICA` | `resp_rate <= 8` | crítico (rojo) |
| `BRADIPNEA` | `resp_rate <= 10` | advertencia (amarillo) |
| `DEFICIT_DE_SUENO_SEVERO` | `sleep_hours < 4.0` | advertencia (amarillo) |
| `DEFICIT_DE_SUENO` | `sleep_hours < 6.0` | advertencia (amarillo) |
| `VARIABILIDAD_CARDIACA_SUPRIMIDA` | `hrv_rmssd <= 15.0` | advertencia (amarillo) |

El frontend **no duplica estos umbrales**: solo mapea cada string de disparador (ya calculado
en Python) a la tarjeta KPI correspondiente y a un nivel visual `warn`/`crit`, vía las tablas
`METRIC_TRIGGERS` y `TRIGGER_SEVERITY` en `static/index.html`. Esto respeta la regla de
arquitectura de `CLAUDE.md`: todo cálculo clínico vive en `engine/`.

Nota: los déficits de sueño no tienen tarjeta KPI propia (las 8 tarjetas no incluyen
`sleep_hours`), pero sus disparadores sí aparecen listados en el panel de Hallazgos Clínicos.

## 6. Asignación del color de alerta NASA (`nasa_alert_color`)

Lógica de `AerospaceHealthEngine._assign_alert_color`:

1. **ROJO** si hay al menos un disparador "crítico" (conjunto `CRITICAL_TRIGGERS`: todos los
   marcados como crítico en la tabla anterior), **o** si `primary_prediction ==
   EVENTO_CARDIOVASCULAR` con `confidence_pct >= 50%`.
2. **AMARILLO** si hay cualquier disparador clínico (crítico o no), o `unsupervised_anomaly ==
   true`, o `primary_prediction != NOMINAL`.
3. **VERDE** en cualquier otro caso.

## 7. Mapeo de datos a componentes visuales

| Componente | Datos que consume |
|---|---|
| Badge de conexión WS | Estado del `WebSocket` del navegador (`ONLINE`/`RECONECTANDO`), no viene del backend |
| Barra de control | Botones `POST /stream/start/{escenario}`, `POST /stream/stop`, botón de persistencia (`GET`/`POST /persistence/*`) |
| Banner de Triaje | `nasa_alert_color`, `primary_prediction`, `confidence_pct`, `unsupervised_anomaly`, `astronaut_id` |
| 8 tarjetas KPI | `raw_telemetry.{hr, hrv_rmssd, spo2, sbp, dbp, temp_c, resp_rate}` + `derived_metrics.{shock_index, pulse_pressure}`; resaltado por `clinical_triggers` |
| Gráfica 1 — Cardiovascular y Oxigenación | `raw_telemetry.hr` (eje izq.) y `raw_telemetry.spo2` (eje der.), ventana móvil de 25 puntos |
| Gráfica 2 — Estrés Autonómico y Hemodinámica | `raw_telemetry.hrv_rmssd` (eje izq.) y `raw_telemetry.sbp` (eje der.), ventana móvil de 25 puntos |
| Gráfica 3 — Distribución de Probabilidades ML | `probabilities` (las 5 clases, x100 para %), barra de la clase ganadora coloreada según `nasa_alert_color` |
| Panel Hallazgos Clínicos | `clinical_triggers` (lista completa, sin filtrar) |
| Panel Reporte SBAR | `report_text`, `alert_color`, `diagnosis`, `inference_time_sec` del mensaje `sbar_report`; muestra spinner "Generando análisis clínico con Llama 3.2..." entre la transición de alerta y la llegada del reporte |

Las gráficas se inicializan con `GET /history` (últimas 30 lecturas en memoria, recortadas a
los últimos 25 puntos) al cargar la página, y luego se actualizan en vivo por WebSocket.

## 8. Mensajes del WebSocket (`/ws/telemetry`)

```json
{"type": "telemetry", "data": { ...DiagnosticOutput... }}
{"type": "sbar_report", "data": { ...SBARReport... }}
```

`SBARReport` contiene: `astronaut_id`, `alert_color`, `diagnosis`, `report_text` (las 4
secciones SBAR en español), `inference_time_sec`, `generated_at`.

## 9. Origen de los datos simulados (no son datos reales de ningún astronauta)

`simulator.scenarios.LiveTelemetryStream` genera, cada 1.2s, un paseo aleatorio con reversión
a la media (`drift_rate = 0.22`) alrededor de un perfil objetivo por escenario
(`LIVE_SCENARIO_PROFILES`), de modo que la variación entre lecturas consecutivas sea fisiológicamente
suave en vez de ruido independiente.

| Escenario (botón) | `environment` | Estado fisiológico objetivo aproximado |
|---|---|---|
| `nominal` | `STATION` | HR ~68 bpm, SpO2 ~98%, HRV ~56 ms — reposo saludable |
| `ansiedad` | `SPACECRAFT` | HR ~122 bpm, HRV ~18 ms, resp. ~27 rpm — crisis de ansiedad |
| `cardiovascular` | `ROVER` | HR ~130 bpm, SpO2 ~88%, SBP ~82 mmHg — evento cardiovascular |
| `infeccion` | `LUNAR_BASE` | Temp ~39.0 °C, HR ~104 bpm, SpO2 ~94% — infección sistémica |

Estos rangos están calibrados para solapar con los `CLASS_PROFILES` de entrenamiento del
clasificador (`engine/predictor.py`), de modo que el modelo ML tienda a reconocer la clase
correcta para cada escenario simulado.

## 10. Persistencia opcional en Postgres (`db/connection.py`)

Independiente del historial en memoria (`GET /history`, 30 lecturas, se pierde al reiniciar el
servidor). Solo se escribe cuando el botón "Guardado en BD" está activo
(`POST /persistence/start`), por defecto está **apagado**.

Tabla `telemetry_readings`:

| Columna | Tipo | Contenido |
|---|---|---|
| `id` | `BIGSERIAL` | PK autoincremental |
| `astronaut_id` | `TEXT` | `DiagnosticOutput.astronaut_id` |
| `scenario` | `TEXT` | escenario activo (`nominal`/`ansiedad`/`cardiovascular`/`infeccion`) o `NULL` |
| `source` | `TEXT` | `"stream"` (flujo continuo) o `"simulate"` (disparo instantáneo) |
| `nasa_alert_color` | `TEXT` | color de alerta |
| `primary_prediction` | `TEXT` | clase principal |
| `confidence_pct` | `DOUBLE PRECISION` | confianza del modelo |
| `unsupervised_anomaly` | `BOOLEAN` | resultado del `IsolationForest` |
| `clinical_triggers` | `JSONB` | lista de disparadores |
| `probabilities` | `JSONB` | distribución completa por clase |
| `derived_metrics` | `JSONB` | `shock_index`, `pulse_pressure`, `hr_slope`, `spo2_slope`, z-scores |
| `raw_telemetry` | `JSONB` | `TelemetryInput` completo |
| `recorded_at` | `TIMESTAMPTZ` | default `now()` |

Interfaz web: Adminer en `http://localhost:8080` (servidor `db`, credenciales en
`.env.example`).

## 11. Endpoints relevantes

| Endpoint | Método | Devuelve / hace |
|---|---|---|
| `/` | GET | Sirve `static/index.html` |
| `/history` | GET | Últimas 30 `DiagnosticOutput` en memoria |
| `/analyze` | POST | Evalúa una `TelemetryInput` puntual, sin tocar historial ni WS |
| `/report` | POST | Genera un `SBARReport` puntual a partir de un `DiagnosticOutput` dado |
| `/simulate/{escenario}` | POST | Dispara una secuencia fija de 3 lecturas, transmite por WS y guarda si la persistencia está activa |
| `/stream/start/{escenario}` | POST | Arranca/reemplaza el flujo continuo (1.2s) |
| `/stream/stop` | POST | Detiene el flujo continuo |
| `/persistence/start` | POST | Conecta a Postgres (si no estaba) y activa el guardado |
| `/persistence/stop` | POST | Desactiva el guardado (no cierra la conexión) |
| `/persistence/status` | GET | `{enabled, connected, saved_count, last_error}` |
| `/ws/telemetry` | WS | Canal de difusión de `telemetry` y `sbar_report` |
