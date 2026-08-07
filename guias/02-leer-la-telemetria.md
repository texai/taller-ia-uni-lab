# Leer la telemetría

**Guía 2 · Taller 02 de caso aplicado de IA en industria**

Tres señales, y las tres se leen mal de tres maneras distintas.

---

## Qué emite la flota

Una fila por modelo y por día: 192 modelos × 91 días = **17,472 filas**. Es
todo lo que hay para saber si algo va mal, y es exactamente por lo que nadie
las mira — no hay forma de leer diecisiete mil filas un lunes por la mañana.

Cada fila lleva el `modelo_id` (`dem-<categoria>-<tienda>`, por ejemplo
`dem-panaderia-callao`), las tres señales —`mape`, `sesgo_pct` y `cobertura`—,
las unidades reales y pronosticadas, y el contexto del día: si hubo promoción o
si hubo quiebre de stock.

Las unidades están **además** de los porcentajes, y no es redundancia: sin
ellas no se puede agregar bien. Por qué, más abajo.

---

## MAPE · cuánto se equivoca

El error porcentual absoluto medio: para cada día, la diferencia entre lo
pronosticado y lo vendido **en valor absoluto**, dividida entre lo vendido. Es
una distancia, no una dirección: un modelo que se pasa por 10 unidades y otro
que se queda corto por 10 tienen exactamente el mismo MAPE.

> **Cómo se lee mal:** es la métrica que está en todos los tableros, y es la
> única de las tres que no se entera del problema más caro del taller. Cientos
> de errores que empujan todos hacia el mismo lado se ven igual que cientos que
> se cancelan entre sí.

---

## Sesgo · hacia qué lado

La misma resta, **sin el valor absoluto**. Positivo significa pronosticar de
más — y pronosticar de más durante tres semanas es inventario que alguien
compró y nadie vendió.

> **Cómo se lee mal: el sesgo no se promedia.** El sesgo de un grupo no es la
> media de los sesgos de sus partes: es la diferencia de sus **totales**.

Un porcentaje ya es un cociente, y promediar cocientes le da el mismo peso a
una tienda de Lima que a una de provincia con la décima parte del volumen. Por
eso las unidades viajan junto a los porcentajes: para poder sumar arriba y
dividir una sola vez, al final.

---

## Cobertura · si el modelo dice la verdad sobre lo que no sabe

Cada predicción viene con un intervalo. La cobertura es qué fracción de los
días la venta real cayó **dentro** de ese intervalo. Si el intervalo promete el
90%, lo esperable ronda 0.9.

> **Cómo se lee mal:** de dos maneras. La primera, confundirla con «días con
> predicción disponible» — no lo es. La segunda, y peor: **97% de cobertura en
> un intervalo del 90% no es estar mejor, es estar peor.** Un intervalo que casi
> nunca falla es tan ancho que no sirve para decidir nada. «Entre 40 y 400
> unidades» nunca se equivoca y nunca ayuda a reponer.

---

## Los cuatro números del mundo sano

Contra estos se lee todo lo demás. Anótalos:

| | |
|---|---|
| MAPE medio | **13.8%** |
| Sesgo de la flota | **+0.8%** |
| Cobertura media | **88.7%** |
| Modelos sobre el umbral | 8 de 192 |

Tu mundo se genera contra la fecha del día, así que tus números se van a
parecer sin ser idénticos. El MAPE y el sesgo coinciden al primer decimal; el
conteo de modelos sobre umbral se mueve.
