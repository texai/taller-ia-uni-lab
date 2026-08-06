"""Ingenieria de features compartida entre entrenamiento e inferencia.

Vive en un solo lugar a proposito: si el entrenamiento y el pronostico calculan
las features de forma distinta, aparece training/serving skew — una de las
fallas mas comunes y mas dificiles de diagnosticar en produccion. Vale la pena
mencionarlo en clase cuando se abra este archivo.
"""

from __future__ import annotations

import pandas as pd

LAGS = (7, 14, 28)
VENTANAS = (7, 28)

COLUMNAS = (
    [f"lag_{d}" for d in LAGS]
    + [f"media_{v}" for v in VENTANAS]
    + [f"dow_{d}" for d in range(1, 7)]
    + ["en_promocion", "t"]
)


def construir_features(serie: pd.DataFrame) -> pd.DataFrame:
    """Recibe una serie diaria ordenada de una tienda-categoria."""
    df = serie.sort_values("fecha").reset_index(drop=True).copy()
    df["fecha"] = pd.to_datetime(df["fecha"])

    for d in LAGS:
        df[f"lag_{d}"] = df["unidades"].shift(d)
    for v in VENTANAS:
        # shift(1) para no filtrar el valor del propio dia que se predice.
        df[f"media_{v}"] = df["unidades"].shift(1).rolling(v).mean()

    dow = df["fecha"].dt.dayofweek
    for d in range(1, 7):
        df[f"dow_{d}"] = (dow == d).astype(int)

    df["en_promocion"] = df["en_promocion"].astype(int)
    df["t"] = range(len(df))
    df["t"] = df["t"] / max(1, len(df))

    return df
