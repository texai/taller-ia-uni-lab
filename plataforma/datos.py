"""Genera el historico de ventas de la cadena.

Es el mundo real simulado: lo que efectivamente se vendio cada dia en cada
tienda y categoria. Los modelos se entrenan sobre una parte de este historico
y despues se los evalua contra el resto.

La serie de cada tienda-categoria combina nivel base, tendencia, estacionalidad
semanal y anual, promociones, quiebres de stock y ruido. Nada exotico: lo justo
para que un modelo razonable acierte y para que, cuando el mundo cambie, falle
de forma reconocible.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta

from plataforma.config import (
    CATEGORIAS,
    REGION_DE,
    RUTA_VENTAS,
    TIENDAS,
)

CAMPOS = [
    "fecha",
    "tienda",
    "region",
    "categoria",
    "unidades",
    "unidades_demandadas",
    "en_promocion",
    "quiebre_stock",
]


def _serie(
    dias: int,
    inicio: date,
    base: float,
    amplitud_semanal: float,
    tamano_tienda: float,
    rng: random.Random,
):
    """Produce (fecha, demandado, vendido, promo, quiebre) dia a dia.

    `demandado` es lo que la gente hubiera comprado; `vendido` es lo que
    realmente se llevo. Cuando hay quiebre de stock los dos difieren, y esa
    diferencia es invisible para el modelo: solo ve lo vendido. Es una de las
    trampas clasicas del pronostico de demanda.
    """
    nivel = base * tamano_tienda
    tendencia = rng.uniform(-0.00035, 0.00075)
    fase_anual = rng.uniform(0, 2 * math.pi)

    dias_promo_restantes = 0
    lift_promo = 1.0

    for i in range(dias):
        dia = inicio + timedelta(days=i)

        # Fin de semana arriba, martes/miercoles abajo.
        dow = dia.weekday()
        factor_semanal = 1 + amplitud_semanal * math.sin(
            2 * math.pi * (dow + 2.5) / 7
        )
        factor_anual = 1 + 0.08 * math.sin(
            2 * math.pi * dia.timetuple().tm_yday / 365 + fase_anual
        )
        factor_tendencia = 1 + tendencia * i

        if dias_promo_restantes == 0 and rng.random() < 0.035:
            dias_promo_restantes = rng.randint(2, 5)
            lift_promo = rng.uniform(1.25, 1.75)
        en_promocion = dias_promo_restantes > 0
        factor_promo = lift_promo if en_promocion else 1.0
        if dias_promo_restantes:
            dias_promo_restantes -= 1

        demandado = (
            nivel
            * factor_semanal
            * factor_anual
            * factor_tendencia
            * factor_promo
            * rng.gauss(1.0, 0.09)
        )
        demandado = max(0.0, demandado)

        # Quiebre de stock: se vende menos de lo que se pidio.
        quiebre = rng.random() < 0.012
        vendido = demandado * rng.uniform(0.45, 0.8) if quiebre else demandado

        yield dia, demandado, vendido, en_promocion, quiebre


def generar(dias: int = 400, semilla: int = 7, hasta: date | None = None) -> int:
    """Escribe el historico completo de ventas y devuelve el numero de filas."""
    rng = random.Random(semilla)
    fin = hasta or date.today()
    inicio = fin - timedelta(days=dias - 1)

    RUTA_VENTAS.parent.mkdir(parents=True, exist_ok=True)
    filas = 0
    with open(RUTA_VENTAS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        for categoria, base, amplitud in CATEGORIAS:
            for tienda, _region, tamano in TIENDAS:
                # Semilla propia por serie: reproducible e independiente.
                rng_serie = random.Random(f"{semilla}-{categoria}-{tienda}")
                for dia, dem, vend, promo, quiebre in _serie(
                    dias, inicio, base, amplitud, tamano, rng_serie
                ):
                    w.writerow(
                        {
                            "fecha": dia.isoformat(),
                            "tienda": tienda,
                            "region": REGION_DE[tienda],
                            "categoria": categoria,
                            "unidades": round(vend, 2),
                            "unidades_demandadas": round(dem, 2),
                            "en_promocion": int(promo),
                            "quiebre_stock": int(quiebre),
                        }
                    )
                    filas += 1
    return filas
