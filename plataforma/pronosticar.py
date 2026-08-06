"""El job batch de pronostico: lo que corre todas las madrugadas en produccion.

Carga los 192 artefactos, proyecta la demanda de cada tienda-categoria y escribe
las predicciones. No hay ningun servicio HTTP: en pronostico de demanda nadie
necesita una respuesta en 50 milisegundos, y este es el patron de despliegue
dominante.

Cada corrida deja una fila en el log del job (corrio, cuanto tardo, si fallo).
El agente tambien vigila eso: un modelo puede estar sano y el job caido.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import date, timedelta

import joblib
import pandas as pd

from plataforma.config import (
    HORIZONTE_DIAS,
    RUTA_MODELOS,
    RUTA_PREDICCIONES,
    RUTA_VENTAS,
    todos_los_modelos,
)
from plataforma.modelo import COLUMNAS, construir_features

CAMPOS = [
    "fecha_corrida",
    "fecha_objetivo",
    "modelo_id",
    "categoria",
    "tienda",
    "region",
    "prediccion",
    "limite_inferior",
    "limite_superior",
    "latencia_ms",
]

RUTA_LOG_JOB = RUTA_PREDICCIONES.parent / "corridas_job.csv"
CAMPOS_JOB = ["fecha_corrida", "estado", "modelos", "predicciones", "duracion_s"]


def _cargar_flota() -> dict:
    ruta = RUTA_MODELOS / "registro.json"
    if not ruta.exists():
        raise FileNotFoundError("No hay flota entrenada. Corre primero: make entrenar")
    registro = json.loads(ruta.read_text(encoding="utf-8"))
    return {r["modelo_id"]: r for r in registro}


def pronosticar(
    desde: date, hasta: date, horizonte: int = HORIZONTE_DIAS, verbose: bool = True
) -> dict:
    """Simula una corrida diaria del job por cada fecha del rango."""
    inicio = time.time()
    ventas = pd.read_csv(RUTA_VENTAS, parse_dates=["fecha"])
    flota = _cargar_flota()

    modelos_cargados = {
        mid: joblib.load(r["artefacto"]) for mid, r in flota.items()
    }

    filas = []
    for m in todos_los_modelos():
        mid = m["modelo_id"]
        if mid not in modelos_cargados:
            continue
        estimador = modelos_cargados[mid]
        serie = ventas[
            (ventas["tienda"] == m["tienda"])
            & (ventas["categoria"] == m["categoria"])
        ]
        df = construir_features(serie)

        # Error historico del modelo, para construir el intervalo.
        sigma = max(1.0, float(df["unidades"].tail(90).std() or 1.0)) * 0.6

        ventana = df[
            (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
        ].dropna(subset=COLUMNAS)
        if ventana.empty:
            continue

        t0 = time.time()
        pred = estimador.predict(ventana[COLUMNAS])
        latencia = int((time.time() - t0) * 1000 / max(1, len(ventana)))

        for (_, fila), p in zip(ventana.iterrows(), pred):
            objetivo = fila["fecha"].date()
            filas.append(
                {
                    "fecha_corrida": (objetivo - timedelta(days=1)).isoformat(),
                    "fecha_objetivo": objetivo.isoformat(),
                    "modelo_id": mid,
                    "categoria": m["categoria"],
                    "tienda": m["tienda"],
                    "region": m["region"],
                    "prediccion": round(float(max(0.0, p)), 2),
                    "limite_inferior": round(float(max(0.0, p - 1.96 * sigma)), 2),
                    "limite_superior": round(float(p + 1.96 * sigma), 2),
                    "latencia_ms": max(1, latencia),
                }
            )

    with open(RUTA_PREDICCIONES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)

    duracion = round(time.time() - inicio, 2)
    nuevo = not RUTA_LOG_JOB.exists()
    with open(RUTA_LOG_JOB, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_JOB)
        if nuevo:
            w.writeheader()
        w.writerow(
            {
                "fecha_corrida": date.today().isoformat(),
                "estado": "ok",
                "modelos": len(modelos_cargados),
                "predicciones": len(filas),
                "duracion_s": duracion,
            }
        )

    if verbose:
        print(f"  {len(filas)} predicciones de {len(modelos_cargados)} modelos")
    return {"predicciones": len(filas), "modelos": len(modelos_cargados), "duracion_s": duracion}
