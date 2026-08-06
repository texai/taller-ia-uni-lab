"""Lo que separa a un agente de un informe: puede ejecutar lo que recomienda.

Y con eso cambia todo. Mientras el agente solo miraba, equivocarse costaba una
alerta de mas. Ahora equivocarse cuesta 24 modelos reentrenados con datos
malos, y un modelo contaminado no se nota hasta la semana siguiente.

Por eso el permiso para actuar NO se le pregunta al modelo de lenguaje. Las
reglas de abajo son codigo: se cumplen aunque el LLM este convencidisimo de lo
contrario, y un prompt no las puede persuadir. El agente propone; estas reglas
disponen.

Es la misma idea que un ingeniero de guardia con acceso restringido: puede
diagnosticar lo que sea, pero hay palancas que no estan a su alcance a las
tres de la manana.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

URL = os.getenv("URL_PLATAFORMA", "http://plataforma:8000")
TIEMPO_ESPERA = 300.0

# Reentrenar es lo unico que se automatiza. "revisar_datos" e "investigar"
# terminan en un humano por definicion: si el agente pudiera cerrarlas solo,
# no serian investigaciones.
ACCIONES_AUTOMATIZABLES = {"reentrenar"}


def _sin_ejecutar(rec: dict, motivo: str) -> dict:
    return {
        "accion": rec.get("accion"),
        "objetivo": rec.get("objetivo"),
        "ejecutada": False,
        "motivo": motivo,
    }


def evaluar(hipotesis: dict, recomendaciones: list[dict]) -> list[dict]:
    """Decide que se ejecuta y que queda para un humano. No llama a nadie.

    Separada de `ejecutar` a proposito: asi la politica se puede leer, probar
    y discutir sin tocar la plataforma, que es justo lo que uno quiere de las
    reglas que le dan la mano a un agente.
    """
    veredicto = []

    # El freno principal. Si el diagnostico es una anomalia, el problema esta
    # en los datos, no en el modelo: reentrenar contra un feed roto ensena
    # ruido y arruina un modelo que estaba sano. Es exactamente el error que
    # el escenario `feed_caido` existe para provocar.
    es_anomalia = hipotesis.get("tipo") == "anomalia"

    for rec in recomendaciones:
        accion = (rec.get("accion") or "").strip()
        if accion not in ACCIONES_AUTOMATIZABLES:
            veredicto.append(_sin_ejecutar(rec, "no es una accion automatizable"))
            continue
        if es_anomalia:
            veredicto.append(
                _sin_ejecutar(
                    rec,
                    "el diagnostico es una anomalia de datos: reentrenar aqui "
                    "contaminaria modelos sanos",
                )
            )
            continue
        if rec.get("urgencia") != "inmediata":
            veredicto.append(
                _sin_ejecutar(rec, "solo se ejecuta lo marcado como inmediata")
            )
            continue

        objetivo = _filtro_de(rec)
        if objetivo is None:
            veredicto.append(
                _sin_ejecutar(rec, "el objetivo no identifica modelos concretos")
            )
            continue

        veredicto.append(
            {
                "accion": accion,
                "objetivo": rec.get("objetivo"),
                "filtro": objetivo,
                "ejecutable": True,
                "justificacion": rec.get("justificacion", ""),
            }
        )
    return veredicto


def _filtro_de(rec: dict) -> dict | None:
    """Traduce el objetivo declarado a un filtro de la API.

    Se exige que la recomendacion venga con `objetivo_tipo` y `objetivo_valor`.
    Adivinar el destino parseando la prosa de "los 24 modelos de panaderia"
    seria pedirle a una expresion regular que decida a que se le borra el
    artefacto.
    """
    tipo = (rec.get("objetivo_tipo") or "").strip()
    valor = (rec.get("objetivo_valor") or "").strip()
    if tipo == "flota":
        return {}
    if tipo in ("categoria", "tienda", "modelo_id") and valor:
        return {tipo: valor}
    return None


def ejecutar(hipotesis: dict, recomendaciones: list[dict]) -> list[dict]:
    """Aplica la politica y dispara lo que sobrevive a ella."""
    resultados = []
    for decision in evaluar(hipotesis, recomendaciones):
        if not decision.get("ejecutable"):
            resultados.append(decision)
            continue
        try:
            r = httpx.post(
                f"{URL}/v1/reentrenar",
                json={
                    **decision["filtro"],
                    "motivo": f"{hipotesis.get('titulo', 'sin titulo')} | "
                    f"{decision.get('justificacion', '')}",
                },
                timeout=TIEMPO_ESPERA,
            )
            r.raise_for_status()
            cuerpo: dict[str, Any] = r.json()
            resultados.append(
                {
                    "accion": decision["accion"],
                    "objetivo": decision["objetivo"],
                    "ejecutada": True,
                    "modelos_reentrenados": cuerpo.get("modelos"),
                    "duracion_s": cuerpo.get("duracion_s"),
                }
            )
        except httpx.HTTPError as e:
            resultados.append(
                {
                    "accion": decision["accion"],
                    "objetivo": decision["objetivo"],
                    "ejecutada": False,
                    "motivo": f"la plataforma rechazo la accion: {e}",
                }
            )
    return resultados
