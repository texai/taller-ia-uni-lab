"""Entrena la flota: un modelo de pronostico por tienda y categoria.

192 artefactos. Cada uno es un Ridge sobre features de calendario, rezagos y
promociones — deliberadamente simple, porque el taller no trata de exprimir
precision sino de vigilar modelos en produccion.

Cada entrenamiento queda registrado en MLflow (almacen de archivos local, sin
servidor) con sus parametros, su metrica de validacion y el artefacto. Es el
mismo registro que usaron en el Modulo 2.
"""

from __future__ import annotations

import json
import os
from datetime import date

import joblib
import pandas as pd
from sklearn.linear_model import Ridge

# MLflow busca el SHA de git para etiquetar cada corrida. Dentro del contenedor
# no hay git, y al no encontrarlo escupe un warning de veinte lineas que parece
# un error grave y no lo es. Se lo decimos antes de importarlo.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

try:
    import mlflow
except ImportError:  # el pipeline no depende del registro para funcionar
    mlflow = None

from plataforma.config import (
    RUTA_MLRUNS,
    RUTA_MODELOS,
    RUTA_VENTAS,
    modelo_id,
    todos_los_modelos,
)
from plataforma.modelo import COLUMNAS, construir_features

EXPERIMENTO = "pronostico-demanda"


def _mape(real: pd.Series, pred: pd.Series) -> float:
    mascara = real > 1e-6
    if not mascara.any():
        return float("nan")
    return float(((real[mascara] - pred[mascara]).abs() / real[mascara]).mean() * 100)


def _registro_previo() -> dict[str, dict]:
    ruta = RUTA_MODELOS / "registro.json"
    if not ruta.exists():
        return {}
    return {r["modelo_id"]: r for r in json.loads(ruta.read_text(encoding="utf-8"))}


def _seleccionar(solo: dict | None) -> list[dict]:
    """Los modelos a entrenar. Sin filtro, la flota entera."""
    modelos = todos_los_modelos()
    if not solo:
        return modelos
    return [
        m
        for m in modelos
        if all(m.get(clave) == valor for clave, valor in solo.items() if valor)
    ]


def entrenar(
    hasta: date,
    alpha: float = 1.0,
    verbose: bool = True,
    solo: dict | None = None,
) -> dict:
    """Entrena la flota con datos hasta `hasta` inclusive.

    `solo` acota a un subconjunto: {"categoria": "panaderia"} reentrena esos
    24 modelos y deja los otros 168 intactos, con su version anterior. Un
    reentrenamiento de produccion casi nunca toca la flota completa: se
    reentrena lo que se degrado, y el registro tiene que reflejar que
    conviven versiones distintas.
    """
    if not RUTA_VENTAS.exists():
        raise FileNotFoundError(
            f"No existe {RUTA_VENTAS}. Corre primero: make datos"
        )

    objetivo = _seleccionar(solo)
    if not objetivo:
        return {"modelos": 0, "entrenado_hasta": hasta.isoformat(), "sin_coincidencias": solo}

    previo = _registro_previo()
    ventas = pd.read_csv(RUTA_VENTAS, parse_dates=["fecha"])
    ventas = ventas[ventas["fecha"].dt.date <= hasta]

    RUTA_MODELOS.mkdir(parents=True, exist_ok=True)
    if mlflow is not None:
        RUTA_MLRUNS.mkdir(parents=True, exist_ok=True)
        mlflow.set_tracking_uri(f"file://{RUTA_MLRUNS}")
        mlflow.set_experiment(EXPERIMENTO)

    registro = []
    for i, m in enumerate(objetivo, start=1):
        serie = ventas[
            (ventas["tienda"] == m["tienda"])
            & (ventas["categoria"] == m["categoria"])
        ]
        df = construir_features(serie).dropna(subset=COLUMNAS)
        if len(df) < 60:
            continue

        # Ultimas 4 semanas como validacion.
        corte = len(df) - 28
        X_tr, y_tr = df[COLUMNAS].iloc[:corte], df["unidades"].iloc[:corte]
        X_va, y_va = df[COLUMNAS].iloc[corte:], df["unidades"].iloc[corte:]

        modelo = Ridge(alpha=alpha).fit(X_tr, y_tr)
        mape_val = _mape(y_va, pd.Series(modelo.predict(X_va), index=y_va.index))

        ruta = RUTA_MODELOS / f"{m['modelo_id']}.joblib"
        joblib.dump(modelo, ruta)

        if mlflow is not None:
            with mlflow.start_run(run_name=m["modelo_id"]):
                mlflow.log_params(
                    {
                        "modelo_id": m["modelo_id"],
                        "categoria": m["categoria"],
                        "tienda": m["tienda"],
                        "region": m["region"],
                        "algoritmo": "Ridge",
                        "alpha": alpha,
                        "entrenado_hasta": hasta.isoformat(),
                        "n_entrenamiento": len(X_tr),
                    }
                )
                mlflow.log_metric("mape_validacion", mape_val)

        registro.append(
            {
                **m,
                "version": previo.get(m["modelo_id"], {}).get("version", 0) + 1,
                "entrenado_hasta": hasta.isoformat(),
                "mape_validacion": round(mape_val, 3),
                "artefacto": str(ruta),
            }
        )
        if verbose and i % 48 == 0:
            print(f"  {i}/{len(objetivo)} modelos entrenados...")

    # Los que no se tocaron conservan su version y su fecha: el registro debe
    # mostrar la flota como esta de verdad, con modelos de distinta edad.
    final = previo | {r["modelo_id"]: r for r in registro}
    (RUTA_MODELOS / "registro.json").write_text(
        json.dumps(
            sorted(final.values(), key=lambda r: r["modelo_id"]),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "modelos": len(registro),
        "entrenado_hasta": hasta.isoformat(),
        "alcance": solo or "flota completa",
        "flota_total": len(final),
    }
