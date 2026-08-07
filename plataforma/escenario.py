"""Degrada el mundo para que los modelos empiecen a fallar.

Los escenarios alteran las ventas *posteriores* a una fecha de corte. Los
modelos se entrenaron con el historico limpio anterior a ese corte, asi que no
saben nada de lo que esta por venir — exactamente lo que pasa en produccion.

Cada escenario falla de una forma distinta a proposito, porque el objetivo
pedagogico es que el agente no pueda salir del paso con una sola regla:

    campana_promocional  MAPE se dispara en UNA categoria, en TODAS las tiendas.
                         El agente debe ver que el patron es por categoria.
    sesgo_silencioso     La demanda cae despacio en TODA la cadena. El MAPE se
                         mueve dentro del ruido; el sesgo se vuelve positivo y
                         sostenido en las ocho categorias. Ningun umbral de
                         MAPE lo detecta. Sobre-stock que nadie factura.
    feed_caido           UNA tienda deja de reportar: sus filas desaparecen,
                         no llegan en cero. Las metricas de la flota se ven
                         sanas. Es una anomalia de datos, no un modelo
                         degradado, y distinguirlo es la gracia.
    quiebre_stock        Faltantes masivos en una categoria: la venta observada
                         queda por debajo de la demanda real y el modelo aprende
                         una demanda deprimida. Espiral descendente.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta

from plataforma.config import NOMBRES_CATEGORIAS, NOMBRES_TIENDAS, RUTA_VENTAS

# Cuanto cae la demanda al final de la ventana en `sesgo_silencioso`.
#
# Calibrado, no elegido a ojo. Una caida pareja mueve el MAPE y el sesgo la
# misma cantidad de puntos; lo que los separa es de donde parten. Con este
# valor el MAPE de la flota va de 13.8 a 14.5 -- ruido -- y los modelos sobre
# el umbral de alerta se duplican, un movimiento por el que nadie levanta el
# telefono. El sesgo, en cambio, va de +0.8% a +4.7%: seis veces, y unas 36 mil
# unidades de sobre-stock.
#
# Cuidado con citar el conteo de modelos y las unidades al detalle. El mundo se
# genera contra la fecha del dia (`datos.py`), asi que esas dos cifras se mueven
# entre ejecuciones: medido con umbral de MAPE > 25% en dos mundos generados con
# cinco dias de diferencia, los modelos sobre umbral van 8 -> 16 en los dos, y
# las unidades dan 36,981 y 36,338. El MAPE y el sesgo, en cambio, coinciden al
# primer decimal.
#
# A 0.18, que es donde estaba, 57 de 192 modelos cruzaban el umbral. Eso ya no
# es silencioso: cualquier tablero lo hubiera gritado, y el escenario dejaba de
# demostrar lo unico que existe para demostrar.
CAIDA_SESGO_SILENCIOSO = 0.06

ESCENARIOS = (
    "campana_promocional",
    "sesgo_silencioso",
    "feed_caido",
    "quiebre_stock",
)


def _leer() -> list[dict]:
    with open(RUTA_VENTAS, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _escribir(filas: list[dict]) -> None:
    with open(RUTA_VENTAS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def aplicar(
    nombre: str,
    desde: date | None = None,
    categoria: str | None = None,
    tienda: str | None = None,
    semilla: int = 11,
    intensidad: float = CAIDA_SESGO_SILENCIOSO,
) -> dict:
    if nombre not in ESCENARIOS:
        raise ValueError(f"Escenario desconocido: {nombre}. Opciones: {ESCENARIOS}")

    filas = _leer()
    fechas = sorted({f["fecha"] for f in filas})
    corte = desde or date.fromisoformat(fechas[-1]) - timedelta(days=27)
    rng = random.Random(semilla)

    categoria = categoria or ("bebidas" if nombre != "quiebre_stock" else "carnes")
    tienda = tienda or "arequipa"
    if categoria not in NOMBRES_CATEGORIAS:
        raise ValueError(f"Categoria desconocida: {categoria}")
    if tienda not in NOMBRES_TIENDAS:
        raise ValueError(f"Tienda desconocida: {tienda}")

    # Un feed caido no reporta ceros: no reporta nada. Las filas desaparecen,
    # igual que en produccion. Es la diferencia entre "vendimos cero" y "no
    # sabemos cuanto vendimos", y el agente tiene que notarla.
    if nombre == "feed_caido":
        muda = corte + timedelta(days=7)
        quedan = [
            f
            for f in filas
            if not (f["tienda"] == tienda and date.fromisoformat(f["fecha"]) >= muda)
        ]
        afectadas = len(filas) - len(quedan)
        _escribir(quedan)
        return {
            "escenario": nombre,
            "desde": muda.isoformat(),
            "categoria": categoria,
            "tienda": tienda,
            "filas_afectadas": afectadas,
        }

    afectadas = 0
    for f in filas:
        fecha = date.fromisoformat(f["fecha"])
        if fecha < corte:
            continue
        avance = (fecha - corte).days / max(1, (date.fromisoformat(fechas[-1]) - corte).days)
        dem = float(f["unidades_demandadas"])
        vend = float(f["unidades"])

        if nombre == "campana_promocional" and f["categoria"] == categoria:
            # Descuentos mucho mas agresivos que cualquiera del entrenamiento.
            lift = 1.0 + 1.4 * rng.uniform(0.8, 1.2)
            dem *= lift
            vend = dem
            f["en_promocion"] = "1"
            afectadas += 1

        elif nombre == "sesgo_silencioso":
            # Caida lenta y pareja en toda la cadena.
            factor = 1.0 - intensidad * avance
            dem *= factor
            vend = dem
            afectadas += 1

        elif nombre == "quiebre_stock" and f["categoria"] == categoria:
            if rng.random() < 0.35 + 0.3 * avance:
                vend = dem * rng.uniform(0.3, 0.6)
                f["quiebre_stock"] = "1"
                afectadas += 1

        f["unidades_demandadas"] = str(round(dem, 2))
        f["unidades"] = str(round(vend, 2))

    _escribir(filas)
    return {
        "escenario": nombre,
        "desde": corte.isoformat(),
        "categoria": categoria,
        "tienda": tienda,
        "filas_afectadas": afectadas,
    }
