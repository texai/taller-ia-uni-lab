# Docker en siete comandos

**Guía 1 · Taller 02 de caso aplicado de IA en industria**

No es un curso de Docker: es la lista de lo que vas a teclear en el taller y
qué hace cada cosa.

---

## Cuatro palabras

| Palabra | Qué es | La pregunta que responde |
|---|---|---|
| **imagen** | La receta congelada: sistema, librerías y código | ¿Qué se va a ejecutar? |
| **contenedor** | Una ejecución de una imagen. Desechable | ¿Dónde se está ejecutando? |
| **volumen** | Disco que sobrevive al contenedor | Si borro el contenedor, ¿dónde quedan mis datos? |
| **servicio** | Cada bloque de `docker-compose.yml`: `plataforma`, `agente`, `ui` | ¿Cómo se llama la pieza? |

**Un modelo no es un contenedor.** En este taller una sola imagen carga los 192
modelos. La relación no es uno a uno, y esa confusión es la que más cuesta
soltar si vienes del taller anterior.

---

## Los siete comandos

| Comando | Qué hace |
|---|---|
| `make arriba` | Construye las tres imágenes y levanta plataforma + interfaz |
| `make seed` | Crea el mundo: datos, entrena 192 modelos, pronostica, mide |
| `make estado` | Qué está corriendo ahora mismo |
| `make ui` | Abre la interfaz en `http://localhost:8501` |
| `make abajo` | Apaga todo, sin borrar nada |
| `make logs` | Sigue los logs. `SERVICIO=agente` para uno solo |
| `make reset` | Botón de pánico: borra **todo**, incluidos los 192 modelos |

`make ayuda` los lista todos, y el `Makefile` enseña qué hay detrás de cada uno
—siempre un `docker compose` que también puedes teclear entero.

> **Ojo con `make reset`.** Borra los volúmenes, así que después hay que volver
> a correr `make seed`: unos minutos. `make abajo` apaga sin borrar, que es lo
> que quieres casi siempre.

---

## `up` contra `run`

Es la distinción que más se confunde. `up` levanta algo y lo **deja vivo**
escuchando; `run --rm` ejecuta **una tarea** y borra el contenedor al terminar.

`make ui` usa `up`. `make seed`, `make agente`, `make plano` y `make verificar`
usan `run --rm`: de esos no queda rastro en `make estado`, y está bien que así
sea — son tareas, no servicios.

---

## Dónde viven tus datos

En el volumen `datos`, montado en `/datos` dentro de los contenedores. **No en
la carpeta del repositorio.** Por eso sobreviven a `make abajo` y por eso
`make reset` los borra.

Ahí dentro hay cinco cosas: `ventas.csv` con el mundo entero —76,800 filas, dos
años de historia—, la carpeta `modelos/` con los 192 artefactos entrenados,
`predicciones.csv` y `metricas.csv` con las 17,472 filas que escribió el job
anoche, y `ejecuciones_job.csv`, su bitácora. De todo eso, lo único que el
agente va a mirar es `metricas.csv`.

Si algo no arranca, la guía 6 lista lo que se rompió montando el laboratorio.
