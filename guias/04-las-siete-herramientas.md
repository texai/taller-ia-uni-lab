# Las siete herramientas del agente

**Guía 4 · Taller 02 de caso aplicado de IA en industria**

Los ojos del agente. Viven en `agente/herramientas.py` y son lo único que el
modelo puede mirar del mundo.

---

## La lista

| Herramienta | Qué devuelve | Cuándo la llama |
|---|---|---|
| `listar_modelos` | El inventario: cuántos, de qué categoría y región | Primero, para saber sobre qué trabaja |
| `resumen_flota` | Salud de los 192: error, sesgo, cobertura y los peores | El punto de partida de cualquier diagnóstico |
| `agregado_por` | Las métricas agregadas por categoría, tienda o región | Para ver la **forma** del problema |
| `comparar_periodos` | Una ventana reciente contra una línea base, con test estadístico | Para decidir si algo **cambió de verdad** |
| `detectar_anomalias` | Series cortadas, tiendas mudas, huecos en los datos | Antes de culpar al modelo |
| `estado_del_job` | Si el job corrió, cuánto tardó, cuántas filas entregó | Un modelo puede estar sano y el job caído |
| `detalle_modelo` | Las métricas diarias de un modelo concreto | Cuando ya sabes cuál mirar de cerca |

---

## Las tres reglas de una herramienta de percepción

1. **Devuelve agregados, no filas.** Decenas de números, no miles. Un modelo de
   lenguaje no puede leer 17,472 filas — y aunque pudiera, no debe.
2. **Es de solo lectura.** En producción nadie le da escritura a un agente
   sobre los modelos.
3. **La estadística la hace Python, no el LLM.** El modelo razona sobre los
   números; no los calcula.

**Y una cuarta, que se descubre usándolas: la docstring es prompt.** No es
documentación. Es lo único que el modelo lee para decidir cuándo llamar cada
herramienta, así que se escribe como se escribe un prompt.

---

## `agregado_por` revela la forma

Es la más útil para diagnosticar, y la razón es que la misma degradación se ve
distinta según por dónde la cortes:

- Se concentra en una **categoría** y aparece en todas las tiendas → la causa
  es del producto.
- Se concentra en una **tienda** y toca todas las categorías → la causa es de
  esa tienda.
- Un modelo suelto degradado → es otra cosa.

Y hay una trampa que vas a ver el sábado. Con la flota **sana**, agrupando por
región, los dos grupos más pequeños —ocho modelos cada uno— ocupan los dos
bordes de la tabla: uno con el sesgo más alto de todos, +8.7%, y otro con el
MAPE más bajo, 10.9. Lima, con 112 modelos, se queda plácidamente en el medio.
Y nada está roto.

**El ruido no tiene signo: tiene tamaño de muestra.** Por eso un umbral único
marca como rotos a los grupos chicos todos los días.

---

## Una herramienta que falla bien

El modelo se va a inventar un identificador —guion bajo donde iba guion— y eso
va a pasar sí o sí. Lo que importa no es que falle: es **qué recibe cuando
falla**. Un «no existe» a secas invita a reintentar con otra variante del
nombre, y ahí se van cinco llamadas.

Nuestras herramientas devuelven, junto al error, el formato esperado del
identificador y una lista de candidatos parecidos. Con eso el modelo corrige a
la primera.

**Una herramienta que falla muda convierte una llamada equivocada en tres.**

---

## Probarlas sin agente

No hace falta un LLM para mirar lo que devuelven: la API está detrás de todas.
En `http://localhost:8000/docs` está la interfaz de Swagger, que permite
lanzarlas desde el navegador y ver la respuesta cruda. Es la forma más cómoda
de entender qué ve el agente antes de dejarlo razonar sobre ello.
