"""La memoria del agente.

Sin memoria, el agente redescubre el mismo problema cada manana y emite la
misma alerta. Con memoria puede decir tres cosas distintas que un dashboard
nunca dice: "esto ya lo reporte", "esto empeoro desde ayer", "esto es nuevo".

Deliberadamente simple: un JSON en disco. Lo que importa pedagogicamente no
es el motor de persistencia, sino que el agente consulte su historial ANTES
de diagnosticar y lo escriba DESPUES.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

RUTA = Path(os.getenv("RUTA_MEMORIA", "/memoria")) / "diagnosticos.json"


def _cargar() -> list[dict]:
    if not RUTA.exists():
        return []
    return json.loads(RUTA.read_text(encoding="utf-8"))


def historial(limite: int = 10) -> list[dict]:
    """Diagnosticos previos, del mas reciente al mas antiguo."""
    return list(reversed(_cargar()))[:limite]


def resumen_para_prompt(limite: int = 5) -> str:
    """Version compacta del historial, para meter en el prompt sin inflarlo."""
    previos = historial(limite)
    if not previos:
        return "No hay diagnosticos previos. Esta es la primera corrida del agente."
    lineas = []
    for d in previos:
        lineas.append(
            f"- [{d['fecha']}] {d['titulo']} "
            f"(severidad: {d['severidad']}, alcance: {d.get('alcance', 'n/d')})"
        )
    return "Diagnosticos previos:\n" + "\n".join(lineas)


def registrar(
    fecha: str,
    titulo: str,
    severidad: str,
    alcance: str,
    evidencia: list[str],
    recomendaciones: list[dict],
) -> dict:
    """Guarda un diagnostico. Devuelve el registro escrito."""
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "fecha": fecha,
        "registrado_en": datetime.now().isoformat(timespec="seconds"),
        "titulo": titulo,
        "severidad": severidad,
        "alcance": alcance,
        "evidencia": evidencia,
        "recomendaciones": recomendaciones,
    }
    todos = _cargar()
    todos.append(registro)
    RUTA.write_text(
        json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return registro


def limpiar() -> int:
    """Borra la memoria. Util para volver a demostrar la primera corrida."""
    n = len(_cargar())
    if RUTA.exists():
        RUTA.unlink()
    return n
