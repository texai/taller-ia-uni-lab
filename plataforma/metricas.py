"""Cruza lo pronosticado contra lo que realmente se vendio.

Sin este paso no hay nada que monitorear: un modelo no se degrada en abstracto,
se degrada contra la realidad. De aqui salen las cuatro senales que el agente
va a interrogar.

    mape       cuanto se equivoca, en porcentaje
    sesgo      hacia que lado se equivoca. Positivo = sobre-pronostica.
               El MAPE puede quedarse quieto mientras el sesgo se dispara:
               ese es el modo de falla mas caro y el que ningun umbral detecta.
    cobertura  que fraccion de los dias cayo dentro del intervalo predicho
    latencia   cuanto tarda el modelo en responder
"""

from __future__ import annotations

import csv
from datetime import date

import pandas as pd

from plataforma.config import RUTA_METRICAS, RUTA_PREDICCIONES, RUTA_VENTAS

CAMPOS = [
    "fecha",
    "modelo_id",
    "categoria",
    "tienda",
    "region",
    "n",
    "mape",
    "sesgo_pct",
    "cobertura",
    "latencia_p95_ms",
    "unidades_reales",
    "dias_en_promocion",
    "dias_con_quiebre",
]


def calcular(desde: date | None = None, hasta: date | None = None) -> dict:
    pred = pd.read_csv(RUTA_PREDICCIONES, parse_dates=["fecha_objetivo"])
    real = pd.read_csv(RUTA_VENTAS, parse_dates=["fecha"])

    df = pred.merge(
        real[
            ["fecha", "tienda", "categoria", "unidades", "en_promocion", "quiebre_stock"]
        ],
        left_on=["fecha_objetivo", "tienda", "categoria"],
        right_on=["fecha", "tienda", "categoria"],
        how="inner",
    )
    if desde is not None:
        df = df[df["fecha_objetivo"].dt.date >= desde]
    if hasta is not None:
        df = df[df["fecha_objetivo"].dt.date <= hasta]

    df["error"] = df["prediccion"] - df["unidades"]
    df["dentro"] = (df["unidades"] >= df["limite_inferior"]) & (
        df["unidades"] <= df["limite_superior"]
    )
    seguro = df["unidades"].clip(lower=1.0)
    df["ape"] = (df["error"].abs() / seguro) * 100
    df["spe"] = (df["error"] / seguro) * 100

    filas = []
    claves = ["fecha_objetivo", "modelo_id", "categoria", "tienda", "region"]
    for (fecha, mid, cat, tienda, region), g in df.groupby(claves, sort=True):
        filas.append(
            {
                "fecha": fecha.date().isoformat(),
                "modelo_id": mid,
                "categoria": cat,
                "tienda": tienda,
                "region": region,
                "n": len(g),
                "mape": round(float(g["ape"].mean()), 3),
                "sesgo_pct": round(float(g["spe"].mean()), 3),
                "cobertura": round(float(g["dentro"].mean()), 4),
                "latencia_p95_ms": int(g["latencia_ms"].quantile(0.95)),
                "unidades_reales": round(float(g["unidades"].sum()), 2),
                "dias_en_promocion": int(g["en_promocion"].sum()),
                "dias_con_quiebre": int(g["quiebre_stock"].sum()),
            }
        )

    with open(RUTA_METRICAS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)

    return {"filas": len(filas), "modelos": df["modelo_id"].nunique()}
