---
marp: true
theme: taller
paginate: true
footer: 'Taller 02 · Caso aplicado de IA en industria · UNI'
---

<!-- _class: portada -->
<!-- _paginate: false -->

# Un agente que vigila 192 modelos

## Arquitectura cognitiva para monitoreo de modelos en producción

Taller 02 · II Programa de Especialización en IA Generativa y MLOps
Ernesto Anaya · 8 y 9 de agosto de 2026

---

## Dónde estamos

Este es el **último curso** del programa. Ya recorrieron:

| Módulo | Lo que trajeron |
|---|---|
| Fundamentos y MLOps | MLflow, DVC, detección de drift |
| Despliegue | FastAPI, Docker, GitHub Actions, Kubernetes |
| Generativa y agentes | LangChain, RAG, LangGraph, ReAct, Reflection |
| Taller 01 | Auditoría de procesos y chatbot de cumplimiento |

Hoy se junta todo: **un agente generativo vigilando modelos desplegados**.

---

<!-- _class: golpe -->

# Empecemos por el caso

No por el agente

---

## Una cadena de retail

**24 tiendas** × **8 categorías** = **192 modelos** de pronóstico de demanda.

Cada madrugada un job los carga, proyecta **14 días**, y con eso se decide
qué reponer en cada tienda.

```
dem-panaderia-callao        dem-lacteos-cusco
dem-bebidas-arequipa        dem-carnes-iquitos
...                         188 más
```

---

## ¿Qué es "un modelo en producción"?

No es un chatbot. Es un **artefacto entrenado** — un `.joblib` con pesos.

- 192 archivos en disco, cada uno con su versión y su fecha de entrenamiento
- **No hay un contenedor por modelo**: un solo job los carga a todos
- La relación modelo ↔ contenedor no es 1 a 1

En la flota conviven modelos de distinta edad. El registro lo dice:
`version: 2` en 168 de ellos, `version: 3` en los 24 que se reentrenaron ayer.

---

## Los modelos funcionan

Hasta que dejan de funcionar. Y fallan de maneras distintas:

| | Qué pasa |
|---|---|
| **Campaña promocional** | Una categoría falla en las 24 tiendas a la vez |
| **Sesgo silencioso** | La demanda cae despacio en toda la cadena |
| **Feed caído** | Una tienda deja de reportar |
| **Quiebre de stock** | La venta observada queda bajo la demanda real |

Cada una exige una respuesta distinta. Y una de ellas exige **no hacer nada**.

---

## Caso 1 · La campaña promocional

Un descuento más agresivo que cualquiera del entrenamiento.

```
bebidas    MAPE  12.9% → 30.2%       en las 24 tiendas
sesgo      -2.0% → -10.5%            sub-pronóstico
```

Sesgo **negativo**: el modelo pronostica de menos.
Menos stock del necesario → **quiebre → venta perdida**.

Esta se ve. El MAPE se dispara y cualquier tablero la muestra.

---

## Caso 2 · El sesgo silencioso

La demanda cae despacio en toda la cadena. El modelo sigue igual.

| Señal | Antes | Después | |
|---|---|---|---|
| MAPE de la flota | 13.8% | 14.5% | *+5%* |
| Modelos sobre el umbral de alerta | 7 / 192 | 14 / 192 | *ruido* |
| **Sesgo de la flota** | **+0.7%** | **+4.7%** | ***×6*** |

---

<!-- _class: dato -->

# 36,567

unidades de más en almacén, en catorce días

Ninguna alarma sonó.

---

## MAPE y sesgo no dicen lo mismo

**MAPE** — cuánto se equivoca. Siempre positivo, siempre ruidoso.

**Sesgo** — hacia **qué lado** se equivoca.

- Sesgo positivo sostenido → sobre-pronóstico → **sobre-stock**
- Sesgo negativo sostenido → sub-pronóstico → **quiebre**

Y hay una asimetría que lo cambia todo:

> En una flota sana el MAPE de una categoría sube hasta **+20%** solo por
> alejarse de su fecha de entrenamiento. El sesgo no se mueve **ni 1.1 puntos**.

Una señal ruidosa y una limpia. Solo una habla de plata.

---

## ¿Por qué no basta un tablero?

Hoy alguien abre un Excel los lunes y revisa las cinco categorías más grandes.

**Los otros 152 modelos nadie los mira.**

Y aunque los mirara: un umbral fijo sobre 192 modelos no distingue
envejecimiento normal de un problema real. Marca 88 de 192 modelos sanos.

Lo que falta no es más datos. Es **criterio**, aplicado 192 veces cada mañana.

---

<!-- _class: golpe -->

# Reto 1

Encuentra el problema a mano

---

## Herramientas de percepción

Un LLM no puede leer 17,472 filas de telemetría. Y aunque pudiera, no debe.

Una herramienta de percepción **agrega y devuelve una lectura**, no datos crudos.

```python
@tool
def comparar_periodos(dias_recientes=14, dias_base=45,
                      dimension="categoria") -> dict:
    """Compara una ventana reciente contra una línea base
    y mide si la diferencia es real."""
```

Siete herramientas. Todas de lectura. Ninguna devuelve una fila.

---

## Tres trampas, todas medidas

**1 · El sesgo no se promedia**
Promediar porcentajes está sesgado hacia arriba. Panadería marcaba **+9.2%**
en un mundo intacto. Como cociente de totales: **+0.7%**.

**2 · Medir lo normal con la ventana que auditas**
Una tienda muda tres semanas tiene mediana cero en esas tres semanas. La avería
pasa por normalidad.

**3 · Significativo ≠ relevante**
Con mil días-modelo, el test de Kolmogorov-Smirnov marca real cualquier cosa.

---

## El umbral depende de por dónde cortes

Medido sobre la flota sana, donde nada está roto:

| dimensión | modelos por grupo | máx Δ MAPE | máx Δ sesgo |
|---|---|---|---|
| categoría | 24 | +19.6% | 1.05 pp |
| región | ~40 | +15.2% | 2.31 pp |
| **tienda** | **8** | **+48.4%** | **3.54 pp** |

Un umbral único calibrado con categorías marca **tres tiendas sanas** como
derivadas. El agente le cree — y hace bien: el error no es suyo.

---

<!-- _class: golpe -->

# Reto 2

Escribe la herramienta

**Criterio**: en la flota sana, cero banderas

---

## Reto 3 · El primer agente

Un bucle ReAct pelado. Un LLM con herramientas, nada más.

```
LLM  ⇄  herramientas
```

Funciona. Llama herramientas, encuentra cosas, suena convincente.

Córranlo tres veces sobre el mismo escenario y comparen.

---

## Lo que le pasa a un bucle sin arquitectura

- Concluye con lo primero que encuentra, sin contrastar contra una línea base
- Ordena por la señal más ruidosa y se queda con los dos números más grandes
- Dramatiza el impacto con cifras que no significan lo que dice
- Mañana redescubre lo mismo y vuelve a alertar

**Nada de esto se arregla con un prompt más largo.**

¿Qué le falta?

---

<!-- _class: portada -->
<!-- _paginate: false -->

# Sesión 2

## La arquitectura cognitiva

Domingo 9 de agosto

---

## Seis capas, un trabajo cada una

```
percepcion → diagnostico → reflexion → recomendacion → accion
     ↑                         │  │          ↑
     └─── (falta evidencia) ───┘  │          │
                                  └→ revision┘
```

| Capa | Su único trabajo |
|---|---|
| **Percepción** | Decide qué mirar. No concluye |
| **Diagnóstico** | Evidencia → hipótesis, con alcance y severidad |
| **Reflexión** | Intenta refutarse |
| **Revisión** | Si la crítica se sostiene, reescribe |
| **Acción** | Ejecuta lo que la política deja pasar |

Más **memoria**, que atraviesa todas.

---

## La forma del problema importa más que su tamaño

- Degradación en **una categoría** a lo largo de todas las tiendas
 → la causa es **del producto**
- En **una tienda** a lo largo de todas las categorías
 → la causa es **de esa tienda**
- En **todas**
 → la causa no es de ninguna: es **de la cadena**

Esto no es un truco de prompt. Es lo que un ingeniero de guardia razona,
escrito donde el agente lo lea.

---

## Memoria

Sin memoria, el agente redescubre el mismo problema cada mañana
y emite la misma alerta.

Con memoria puede decir tres cosas que un tablero nunca dice:

> **esto ya lo reporté** · **esto empeoró desde ayer** · **esto es nuevo**

Lee su historial **antes** de diagnosticar. Lo escribe **después**.

---

## Reflexión

Antes de alertar, el agente intenta refutarse. Esto lo escribió él, sobre
su propio diagnóstico, en una corrida real:

> *"Un delta de MAPE de 19.6% sin bandera significa que el sistema ya evaluó
> eso y lo descartó. No puedo ignorarlo solo porque el número se ve grande."*

> *"Inventé impacto de negocio. Dije '9,436 unidades de sobre-stock' pero eso
> es el error acumulado del pronóstico, no sobre-stock. **Estoy dramatizando**."*

Se acusa de dramatizar. Y se baja la severidad.

---

## Pero objetar no alcanza

En el mundo del sesgo silencioso, el agente reportó `sin_hallazgos`.
Y acto seguido, en su propia crítica:

> *"Tengo banderas de sesgo encendidas en 8/8 categorías y 4/5 regiones.
> Eso NO es ruido normal: es un patrón sistemático."*
> *"**SÍ hay hallazgo: hay DERIVA**."*

Su recomendación también era correcta: reentrenar los 192 modelos.

**Sabía la respuesta. El grafo no le dejaba decirla.**

---

<!-- _class: golpe -->

# Una reflexión que no puede corregir

es decorativa

---

## Revisión

El nodo que faltaba. Cuando la crítica sigue en pie y ya no quedan vueltas:

- Misma evidencia, sin llamar más herramientas
- Reescribir el diagnóstico haciéndose cargo de las objeciones
- Y **decirlo**: la salida marca *"reescrito tras la reflexión"*

Sin él, el titular sale contradiciendo a las recomendaciones impresas debajo.

---

## Acción

Hasta aquí el agente recomienda. Ahora **ejecuta**: dispara el reentrenamiento
de los modelos que él mismo señaló, y queda en bitácora.

```
✓ reentrenar → 24 modelos de panaderia     1.5s
✓ reentrenar → 24 modelos de lacteos       1.4s
```

Y con eso cambia la naturaleza del riesgo.

---

<!-- _class: golpe -->

# Equivocarse deja de costar una alerta

y pasa a costar 24 modelos entrenados con datos malos

---

## El freno va en código

El permiso para actuar **no se le pregunta al modelo de lenguaje**.

```python
# Si el diagnóstico es una anomalía, el problema está en los datos:
# reentrenar contra un feed roto enseña ruido.
es_anomalia = hipotesis.get("tipo") == "anomalia"
```

Dos reglas hacen el trabajo pesado:

- **Naturaleza del problema** — con anomalía, nunca se reentrena
- **Radio de daño** — una categoría son 24 modelos y se deshace entrenando otra
 vez; la flota son 192 y no queda ninguno sano con qué comparar

Un prompt no puede persuadir a un `if`.

---

## La trampa

Escenario `feed_caido`. Una tienda deja de reportar: sus filas **no llegan en
cero, no llegan**.

```
MAPE de la flota    13.73%      ← impecable
Sesgo               +0.66%      ← impecable
Banderas de deriva  ninguna     ← impecable
Anomalías           1           ← arequipa, 21 días sin telemetría
```

Si el agente solo mira drift, no ve nada y se va tranquilo a su casa.
Si recomienda reentrenar, **entrena con datos fantasma**.

---

## Lo que hizo el agente

```
tipo: anomalia · alcance: tienda:arequipa · severidad: media

[inmediata] revisar_datos → Restaurar feed de Arequipa
  "Sin datos de entrada, los 8 modelos de Arequipa no pueden
   evaluar demanda real ni reentrenarse."

ACCIÓN
  ✗ no se ejecutó: no es una acción automatizable
```

No cayó en la trampa. Y aunque hubiera caído, la política lo frenaba.

---

<!-- _class: golpe -->

# Ocho errores construyendo esto

Ninguno estaba en el modelo

---

## Dónde estaban de verdad

**Dos de cableado del grafo**
El contexto no llegaba a la API. El estado no se propagaba entre nodos.

**Uno de un simulador que no podía fallar**
Devolvía un texto fijo, nunca llamaba una herramienta. No verificaba nada.

**Cuatro de estadística bien calculada y mal planteada**
Promediar porcentajes. Medir lo normal con la ventana auditada. Confundir
significancia con relevancia. Ordenar los hallazgos por la métrica ruidosa.

**Uno de un campo sin definir**
`cobertura` sin explicación. El agente gastó tres objeciones peleando con una
contradicción que no existía.

---

## El agente los sufrió todos

Y varios los diagnosticó él mismo, antes que nosotros:

> *"Usé p-valor bajo como evidencia de anomalía de datos, pero p-valor bajo
> solo significa cambio estadísticamente significativo."*

> *"¿Por qué Callao y Arequipa son anomalía y Miraflores no? La diferencia es
> solo de magnitud, no de naturaleza."*

Esa segunda frase es la crítica correcta a un umbral mal calibrado —
escrita por el agente que lo estaba sufriendo.

---

<!-- _class: golpe -->

# Cuando un agente se equivoca,

la primera sospecha no debería ser el modelo.
Casi siempre es lo que le diste de comer.

---

## Lo que se llevan

- Un agente con arquitectura cognitiva, corriendo, con su interfaz
- El criterio para elegir la métrica correcta antes que el umbral correcto
- La diferencia entre deriva y anomalía, y por qué cuesta caro confundirlas
- Una política de acción que no depende de la buena voluntad del modelo

Todo el laboratorio queda en:

**github.com/texai/taller-ia-uni-lab**

```bash
make verificar      # 24 comprobaciones, sin gastar un token
```

---

<!-- _class: portada -->
<!-- _paginate: false -->

# Gracias

## Ernesto Anaya

Taller 02 · Caso aplicado de IA en industria
UNI · Agosto 2026
