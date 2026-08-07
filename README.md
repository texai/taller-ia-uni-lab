# Taller 02 de caso aplicado de IA en industria

**II Programa de Especialización en IA Generativa y Machine Learning Ops**
Sábado 8 de agosto, 15:00–19:00 · Domingo 9 de agosto, 09:00–13:00

---

## El caso

Una cadena de retail con **24 tiendas** y **8 categorías** pronostica su demanda
todas las noches. Un modelo por tienda y categoría: **192 modelos en producción**.
Cada madrugada un job los carga, proyecta los próximos 14 días, y con eso se
decide qué reponer.

Los modelos funcionan. Hasta que dejan de funcionar.

Entra una campaña promocional más agresiva que cualquiera del entrenamiento y
una categoría entera empieza a fallar en las 24 tiendas a la vez. O peor: la
demanda cae despacio en toda la cadena, el modelo sigue pronosticando como
antes, y se acumula sobre-stock durante tres semanas.

Ese segundo caso no dispara ninguna alarma, y vale la pena ver por qué. El
error medio pasa de 13.8% a 14.5%: se mueve menos que entre dos semanas
cualesquiera. Los modelos que cruzan el umbral de alerta pasan de 7 a 14 sobre
192 — nadie levanta el teléfono por eso. Pero el sesgo va de +0.7% a +4.7%, seis
veces, y eso son **36,000 unidades de más** en almacén. Un mismo cambio en el
mundo: una señal apenas tiembla, la otra se multiplica. Solo una de las dos
está hablando de plata.

Hoy alguien abre un Excel los lunes y revisa las cinco tiendas más grandes.
Los otros 152 modelos nadie los mira.

## Lo que vamos a construir

Un **agente generativo con arquitectura cognitiva** que vigila la flota:

| Capa | Qué hace |
|---|---|
| **Percepción** | Consulta la telemetría, calcula drift, detecta anomalías |
| **Memoria** | Recuerda diagnósticos previos: no repite alertas ni se contradice |
| **Razonamiento** | Decide qué mirar, correlaciona señales, formula una hipótesis |
| **Reflexión** | Cuestiona su propio diagnóstico antes de emitirlo |
| **Revisión** | Si la crítica se sostiene, reescribe el diagnóstico |
| **Acción** | Ejecuta lo que una política de código deja pasar, y lo deja en bitácora |

Más una **interfaz web** que muestra su ejecución paso a paso, el análisis y las
recomendaciones.

---

# Trabajo previo — hazlo ANTES del sábado

> Unos 10 minutos, casi todos de descarga: la construcción de las imágenes
> tarda ~3 minutos con buena conexión y `make seed` menos de 1. **No lo dejes
> para el sábado**: si lo haces a las 15:00 vas a pasar la primera hora bajando
> imágenes en vez de construyendo el agente.

## 1. Verifica lo que ya tienes

```bash
docker --version          # Docker 24 o superior
docker compose version    # Compose v2
git --version
```

**Si `docker compose version` responde `unknown command`**, te falta Compose.
Prueba primero con guion, que es la versión antigua:

```bash
docker-compose --version
```

Si tampoco responde, instala [Docker Desktop](https://www.docker.com/products/docker-desktop/),
que trae Compose incluido. El `Makefile` detecta solo cuál de los dos tienes,
así que con cualquiera de los dos los comandos de abajo funcionan igual.

## 2. Levanta el entorno

```bash
git clone https://github.com/texai/taller-ia-uni-lab.git
cd taller-ia-uni-lab
cp .env.example .env
make arriba
make seed
```

`make arriba` construye las imágenes la primera vez (~3 min) y levanta la
plataforma. `make seed` genera el histórico de ventas, entrena los 192 modelos,
corre el job de pronóstico y calcula las métricas (~1 min).

Al final debes ver:

```
Listo. 192 modelos con 17,472 dias-modelo de telemetria.
```

## 3. Consigue tu llave

Abre `.env` y completa **solo la línea de tu proveedor**:

```dotenv
PROVEEDOR_LLM=google
MODELO_LLM=gemini-2.0-flash
GOOGLE_API_KEY=...
```

**Opciones gratuitas** (recomendadas — sácala antes del sábado):

- **Google AI Studio** → [aistudio.google.com](https://aistudio.google.com) · llave instantánea con tu cuenta de Google
- **Groq** → [console.groq.com](https://console.groq.com) · llave instantánea

Si ya pagas OpenAI o Anthropic, también funcionan. Y si prefieres no usar
ninguna nube:

```bash
make ollama       # descarga ~2 GB, hazlo antes del sábado
# y en .env:  PROVEEDOR_LLM=ollama
```

Último recurso para no quedarte trabado: `PROVEEDOR_LLM=mock`.

## 4. Verifica

Abre **http://localhost:8501**. Debes ver un mensaje verde con *192 modelos en
producción* y un gráfico de MAPE por categoría.

Si lo ves, estás listo. Si no, escribe **antes del sábado** al foro del aula
virtual con el error exacto que te aparece.

---

## Referencia

```bash
make              # lista todos los comandos disponibles   (macOS / Linux)
.\taller.ps1      # lo mismo, desde PowerShell             (Windows)
```

> **Windows:** `make` no viene con el sistema. `taller.ps1` hace exactamente lo
> mismo desde PowerShell, sin necesidad de WSL2. Donde este README diga
> `make X`, tú escribes `.\taller.ps1 X`.

| Comando | Qué hace |
|---|---|
| `make arriba` / `make abajo` | Levanta o apaga el entorno |
| `make seed` | Pipeline completo desde cero |
| `make datos` | Genera el histórico de ventas |
| `make entrenar` | Entrena los 192 modelos |
| `make pronosticar` | Corre el job batch |
| `make metricas` | Cruza pronóstico contra realidad |
| `make agente` | Una ejecución del agente (el grafo completo) |
| `make plano` | El bucle ReAct del reto 3, sin grafo |
| `make agente ARGS="--verboso"` | Una ejecución mostrando las herramientas que llamó |
| `make memoria` | Qué diagnósticos recuerda el agente |
| `make memoria ARGS="--limpiar"` | Borra la memoria |
| `make actuar` | Ejecución **con permiso para reentrenar de verdad** |
| `make ui` | Interfaz en http://localhost:8501 |
| `make mlflow` | Registro de modelos en http://localhost:5000 |
| `make romper ESCENARIO=...` | Degrada los datos: rompe el mundo |
| `make reparar` | Regenera los datos limpios: vuelve al mundo sano |
| `make reset` | Botón de pánico: borra todo y reconstruye |
| `make verificar` | Comprueba que todo el laboratorio funciona |
| `make verificar ARGS="--con-llm"` | Ídem, corriendo el agente de verdad |

**Escenarios de degradación:** `campana_promocional`, `sesgo_silencioso`,
`feed_caido`, `quiebre_stock`.

**API de la plataforma** — `http://localhost:8000/docs` para explorarla:

| Endpoint | Devuelve |
|---|---|
| `GET /v1/modelos` | Inventario de la flota |
| `GET /v1/metricas` | Métricas diarias por modelo |
| `GET /v1/series/{modelo_id}` | Pronóstico contra realidad de un modelo |
| `GET /v1/job/ejecuciones` | Historial del job batch |
| `POST /v1/reentrenar` | La única ruta que escribe: reentrena un subconjunto |
| `GET /v1/reentrenamientos` | Bitácora de lo que se reentrenó, cuándo y por qué |

---

## Nota sobre los datos

El histórico es **sintético** y la cadena es ficticia. La mecánica de
degradación sí reproduce modos de falla reales de sistemas de pronóstico en
producción. Lo que aprendas acá es transferible: el agente sirve para vigilar
cualquier flota de modelos que emita predicciones evaluables contra la realidad.
