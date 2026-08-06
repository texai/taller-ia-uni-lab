"""Telemetria de la plataforma, y la unica puerta por la que se puede actuar.

El agente no toca los artefactos ni los contenedores: interroga esta API, igual
que haria un ingeniero de guardia. Casi todo lo que hay aca es de lectura.

La excepcion es `POST /v1/reentrenar`, y su superficie es deliberadamente
angosta: una sola ruta que escribe, con filtro explicito, motivo obligatorio y
bitacora. Un agente que solo observa no puede romper nada; en cuanto puede
actuar, el riesgo cambia de naturaleza y conviene que quepa entero en un
archivo que alguien pueda leer de una sentada.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from plataforma.config import (
    RUTA_LOG_REENTRENAMIENTOS,
    RUTA_METRICAS,
    RUTA_MODELOS,
    RUTA_PREDICCIONES,
    RUTA_VENTAS,
)
from plataforma.entrenar import entrenar
from plataforma.pronosticar import RUTA_LOG_JOB

app = FastAPI(
    title="Plataforma de pronostico de demanda",
    description="Flota de 192 modelos en produccion y su telemetria.",
    version="1.0.0",
)

NUMERICOS = {
    "n": int,
    "mape": float,
    "sesgo_pct": float,
    "cobertura": float,
    "latencia_p95_ms": int,
    "unidades_reales": float,
    "unidades_pronosticadas": float,
    "dias_en_promocion": int,
    "dias_con_quiebre": int,
}


def _leer_csv(ruta, tipos: dict | None = None) -> list[dict[str, Any]]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    for f in filas:
        for col, tipo in (tipos or {}).items():
            if col in f and f[col] != "":
                f[col] = tipo(f[col])
    return filas


@app.get("/salud")
def salud() -> dict[str, Any]:
    metricas = _leer_csv(RUTA_METRICAS)
    return {
        "estado": "ok",
        "ventas": RUTA_VENTAS.exists(),
        "predicciones": RUTA_PREDICCIONES.exists(),
        "filas_metricas": len(metricas),
        "modelos": len({f["modelo_id"] for f in metricas}),
    }


@app.get("/v1/modelos")
def modelos() -> list[dict[str, Any]]:
    """Inventario de la flota: que modelos existen, de que version y con que
    metrica de validacion quedaron."""
    ruta = RUTA_MODELOS / "registro.json"
    if not ruta.exists():
        raise HTTPException(503, "Flota sin entrenar. Corre: make entrenar")
    return json.loads(ruta.read_text(encoding="utf-8"))


@app.get("/v1/metricas")
def metricas(
    modelo_id: str | None = None,
    categoria: str | None = None,
    tienda: str | None = None,
    region: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = Query(20000, le=200000),
) -> list[dict[str, Any]]:
    """Metricas diarias por modelo. Es la materia prima del diagnostico."""
    salida = []
    for f in _leer_csv(RUTA_METRICAS, NUMERICOS):
        if modelo_id and f["modelo_id"] != modelo_id:
            continue
        if categoria and f["categoria"] != categoria:
            continue
        if tienda and f["tienda"] != tienda:
            continue
        if region and f["region"] != region:
            continue
        fecha = date.fromisoformat(f["fecha"])
        if desde and fecha < desde:
            continue
        if hasta and fecha > hasta:
            continue
        salida.append(f)
        if len(salida) >= limite:
            break
    return salida


@app.get("/v1/series/{modelo_id}")
def serie(modelo_id: str, dias: int = 90) -> dict[str, Any]:
    """Pronostico contra realidad de un modelo puntual, para mirarlo de cerca."""
    pred = [f for f in _leer_csv(RUTA_PREDICCIONES) if f["modelo_id"] == modelo_id]
    if not pred:
        raise HTTPException(404, f"Sin predicciones para {modelo_id}")
    pred = pred[-dias:]
    partes = modelo_id.split("-")
    tienda = partes[-1]
    categoria = "-".join(partes[1:-1])
    real = {
        f["fecha"]: float(f["unidades"])
        for f in _leer_csv(RUTA_VENTAS)
        if f["tienda"] == tienda and f["categoria"] == categoria
    }
    return {
        "modelo_id": modelo_id,
        "puntos": [
            {
                "fecha": p["fecha_objetivo"],
                "prediccion": float(p["prediccion"]),
                "real": real.get(p["fecha_objetivo"]),
                "limite_inferior": float(p["limite_inferior"]),
                "limite_superior": float(p["limite_superior"]),
            }
            for p in pred
        ],
    }


@app.get("/v1/job/corridas")
def corridas() -> list[dict[str, Any]]:
    """Historial del job batch. Un modelo puede estar sano y el job caido."""
    return _leer_csv(RUTA_LOG_JOB)


class PeticionReentrenamiento(BaseModel):
    """A quien reentrenar. Sin filtros, la flota completa."""

    categoria: str | None = None
    tienda: str | None = None
    modelo_id: str | None = None
    motivo: str = "sin motivo declarado"


@app.post("/v1/reentrenar")
def reentrenar(peticion: PeticionReentrenamiento) -> dict[str, Any]:
    """Reentrena los modelos que coincidan con el filtro.

    Es la unica ruta de la API que escribe. Todo lo demas es telemetria de
    lectura: un agente que solo observa no puede romper nada, y en el momento
    en que puede actuar el riesgo cambia de naturaleza.
    """
    solo = {
        k: v
        for k, v in (
            ("categoria", peticion.categoria),
            ("tienda", peticion.tienda),
            ("modelo_id", peticion.modelo_id),
        )
        if v
    }
    inicio = datetime.now()
    resultado = entrenar(hasta=date.today(), verbose=False, solo=solo)
    if not resultado["modelos"]:
        raise HTTPException(404, f"Ningun modelo coincide con {solo}")

    registro = {
        "momento": inicio.isoformat(timespec="seconds"),
        "duracion_s": round((datetime.now() - inicio).total_seconds(), 1),
        "motivo": peticion.motivo,
        **resultado,
    }
    RUTA_LOG_REENTRENAMIENTOS.parent.mkdir(parents=True, exist_ok=True)
    historial = []
    if RUTA_LOG_REENTRENAMIENTOS.exists():
        historial = json.loads(RUTA_LOG_REENTRENAMIENTOS.read_text(encoding="utf-8"))
    historial.append(registro)
    RUTA_LOG_REENTRENAMIENTOS.write_text(
        json.dumps(historial, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return registro


@app.get("/v1/reentrenamientos")
def reentrenamientos() -> list[dict[str, Any]]:
    """Que se reentreno, cuando y por que. La bitacora de las acciones."""
    if not RUTA_LOG_REENTRENAMIENTOS.exists():
        return []
    return json.loads(RUTA_LOG_REENTRENAMIENTOS.read_text(encoding="utf-8"))
