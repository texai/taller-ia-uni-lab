# Los cinco retos

Ocho horas, dos sesiones. Al final tienes un agente con arquitectura cognitiva
vigilando 192 modelos en producción, y una interfaz que muestra cómo razona.

| | Reto | Qué construyes | Tiempo |
|---|---|---|---|
| **S1** | 1 | Encontrar el problema a mano | 40 min |
| **S1** | 2 | Una herramienta de percepción | 60 min |
| **S1** | 3 | El primer agente, sin arquitectura | 60 min |
| **S2** | 4 | La arquitectura cognitiva | 90 min |
| **S2** | 5 | De la recomendación a la acción | 60 min |

Cada reto tiene su rama de solución: `reto-1-solucion`, `reto-2-solucion`, etc.
Si te trabas, no pierdas la clase peleando:

```bash
git stash              # guarda lo tuyo, no lo pierdes
git checkout reto-2-solucion
```

---

## Sesión 1 · Sábado 15:00–19:00

### Reto 1 — Encuentra el problema a mano

**40 minutos.** Sin agente, sin LLM. Solo tú, la API y pandas.

La cadena tiene 192 modelos de pronóstico en producción. Uno de ellos —o
muchos— se está portando mal. Tu trabajo es encontrarlo con las herramientas
de siempre.

```bash
make romper ESCENARIO=campana_promocional
```

Abre `http://localhost:8000/docs` y explora la telemetría. Responde:

1. ¿Cuál es el MAPE medio de la flota en los últimos 14 días?
2. ¿Qué categoría está peor? ¿En cuántas tiendas?
3. ¿El problema es de esa categoría, de una región, o de la cadena entera?

Después:

```bash
make reparar
make romper ESCENARIO=sesgo_silencioso
```

Y responde lo mismo. **Aquí está el punto del reto**: con este segundo
escenario, el MAPE de la flota pasa de 13.8% a 14.5% y los modelos que cruzan
el umbral de alerta pasan de 7 a 14 sobre 192. Si tu tablero alerta por MAPE,
no suena nada.

Pero el sesgo pasa de +0.7% a +4.7%. Son **más de 36,000 unidades de más** en
almacén en catorce días.

> El MAPE y el sesgo son estables entre ejecuciones; la cifra exacta de unidades y
> el conteo de modelos sobre el umbral no lo son. El mundo se genera contra la
> fecha del día (`datos.py`, `fin = hasta or date.today()`), así que tu número
> va a parecerse al de acá sin ser idéntico. Medido en dos mundos generados con
> cinco días de diferencia: 36,338 y 36,981 unidades.

> **La pregunta que te llevas**: hiciste esto para dos escenarios y una
> categoría. Ahora hazlo cada mañana, para 192 modelos, en ocho categorías,
> veinticuatro tiendas y cinco regiones. ¿Cuánto tardas? ¿Y cuántos lunes
> aguantas antes de mirar solo las cinco tiendas más grandes?

---

### Reto 2 — Una herramienta de percepción

**60 minutos.** Escribes la primera pieza del agente.

Un LLM no puede leer 17,472 filas de telemetría, y aunque pudiera, no debe: se
las tragaría enteras para responder "¿cómo va la flota?". Una herramienta de
percepción **agrega** y devuelve una lectura, no datos crudos.

Vas a escribir `comparar_periodos`: compara una ventana reciente contra una
línea base anterior y dice si la diferencia es real.

Lo que tiene que salir bien, y es donde casi todos tropiezan:

- **El sesgo no se promedia.** El sesgo de un grupo no es el promedio de los
  sesgos de sus partes: es la diferencia de sus totales. Promediar porcentajes
  está sesgado hacia arriba, y con datos reales una categoría con muchas
  promociones parecerá sobre-pronosticada aunque no lo esté.
- **Significativo no es lo mismo que relevante.** Con mil días-modelo, un test
  estadístico marca real cualquier cosa. Toda la flota pierde precisión al
  alejarse de su fecha de entrenamiento —hasta +20% de MAPE en un mundo
  intacto— y eso es envejecimiento, no una alarma.
- **El umbral depende de por dónde cortes.** Una categoría agrupa 24 modelos;
  una tienda, 8. El promedio de la tienda salta mucho más por puro azar.

**Criterio de aceptación**: con `make reparar`, tu herramienta no enciende
ninguna bandera. Ninguna. Si la flota sana dispara alarmas, el agente que
construyas encima no tiene salvación.

---

### Reto 3 — El primer agente, sin arquitectura

**60 minutos.** Un bucle ReAct pelado: un LLM con herramientas, y nada más.

```
LLM  ⇄  herramientas
```

Le das tus herramientas de percepción y le preguntas cómo va la flota. Va a
funcionar. Va a llamar herramientas, va a encontrar cosas, va a sonar
convincente.

Corre el mismo escenario tres o cuatro veces y compara las salidas. Lo que vas
a ver, y es el material de la Sesión 2:

- Concluye con lo primero que encuentra y no contrasta contra una línea base.
- Ordena por la señal más ruidosa y se queda con los dos números más grandes.
- Dramatiza el impacto de negocio con cifras que no significan lo que dice.
- Mañana redescubre lo mismo y vuelve a alertar, sin saber que ya lo reportó.

> **La pregunta que te llevas**: nada de esto se arregla con un prompt más
> largo. ¿Qué le falta a este bucle?

---

## Sesión 2 · Domingo 09:00–13:00

### Reto 4 — La arquitectura cognitiva

**90 minutos.** El corazón del taller.

Conviertes el bucle en un grafo donde cada nodo tiene un trabajo y solo uno:

```
percepcion  →  diagnostico  →  reflexion  →  recomendacion
     ↑                            │   │           ↑
     └──── (falta evidencia) ─────┘   └→ revision ┘
```

- **percepción** — decide qué mirar y llama herramientas. No concluye nada.
- **diagnóstico** — convierte evidencia en hipótesis, con alcance y severidad.
- **reflexión** — intenta refutarse. Si le falta evidencia, vuelve a percibir.
- **revisión** — si la crítica se sostiene y ya no quedan vueltas, reescribe
  el diagnóstico haciéndose cargo de ella.
- **recomendación** — acciones concretas.

Más **memoria**: el agente lee su historial antes de diagnosticar y lo escribe
después. Sin eso no puede decir las tres cosas que un tablero nunca dice —
*esto ya lo reporté*, *esto empeoró desde ayer*, *esto es nuevo*.

**Por qué existe `revisión`.** Una reflexión que solo puede objetar es
decorativa. Sin ese nodo, cuando la crítica demuele el diagnóstico y se acaban
las vueltas, el agente emite igual la hipótesis demolida: el titular termina
contradiciendo a las recomendaciones impresas debajo. Pasó de verdad
construyendo este taller, y es la razón de que el nodo esté ahí.

**Criterio de aceptación** — cuatro mundos, cuatro lecturas distintas:

| escenario | lo que debe decir |
|---|---|
| sano | `sin_hallazgos`, severidad baja |
| campana_promocional | `deriva`, `categoria:bebidas` |
| sesgo_silencioso | `deriva`, `flota`, las 8 categorías, reentrenar |
| feed_caido | `anomalia`, `tienda:arequipa`, **NO** reentrenar |

El último es la trampa. Una tienda dejó de reportar: sus filas no llegan en
cero, no llegan. Las métricas de la flota se ven impecables. Si el agente
recomienda reentrenar, entrena con datos fantasma y empeora un modelo que
estaba sano.

---

### Reto 5 — De la recomendación a la acción

**60 minutos.** Lo que separa a un agente de un informe.

Hasta aquí el agente recomienda. Ahora actúa: dispara el reentrenamiento de
los modelos que él mismo señaló, y lo deja registrado.

Y construyes la interfaz: la ejecución paso a paso, qué herramientas llamó,
el diagnóstico, la crítica, la corrección si la hubo, y las recomendaciones.

**La parte que importa no es el botón, es el freno.** Un agente que reentrena
solo, sobre un diagnóstico equivocado, hace más daño que uno que no hace nada.
Antes de actuar tiene que pasar por su propia reflexión, y hay una acción que
nunca debe ejecutarse sola: reentrenar cuando el problema es de datos.

---

## Lo que te llevas

Siete errores se encontraron construyendo este laboratorio. Ninguno estaba en
el modelo de lenguaje:

- dos de cableado del grafo — el contexto no llegaba, el estado no se propagaba
- uno de un simulador que no podía fallar, y por eso no verificaba nada
- cuatro de estadística bien calculada y mal planteada — promediar porcentajes,
  medir lo normal con la ventana que auditas, confundir significancia con
  relevancia, ordenar los hallazgos por la métrica ruidosa

El agente los sufrió todos. Varios los diagnosticó él mismo en su reflexión,
antes que nosotros.

**Cuando un agente se equivoca, la primera sospecha no debería ser el modelo.**
Casi siempre es lo que le diste de comer.
