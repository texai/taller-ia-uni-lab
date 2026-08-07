"""El bucle ReAct plano: un LLM con herramientas, y nada mas.

Es el reto 3, y existe como archivo aparte por una razon de contenido y no de
codigo: el sabado hay que ver ESTO correr, no el grafo. Con `make agente` la
sala veria al agente criticarse y corregirse, que es justo la revelacion del
domingo, y las cuatro patologias que el reto 3 tiene que demostrar no
aparecerian nunca -- porque la arquitectura ya las corrige.

Pensar, actuar, observar, repetir. No hay mas. Ni un nodo que critique, ni uno
que reescriba, ni nada que persista entre ejecuciones: cuando la clase pregunta
que le falta, la respuesta esta en lo que este archivo NO tiene.

    make plano
    make plano ARGS="--fecha 2026-08-08"
"""

from __future__ import annotations

import argparse
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agente.grafo import CONTEXTO
from agente.herramientas import HERRAMIENTAS
from agente.llm import obtener_llm

# Un tope, y no porque el bucle deba pararse solo: sin el, un modelo que se
# empeña en llamar herramientas gasta la llave de veinte alumnos en una tarde.
# Que haga falta un tope arbitrario es, en si mismo, parte de la leccion.
MAX_VUELTAS = 12

POR_NOMBRE = {h.name: h for h in HERRAMIENTAS}


def correr(fecha: date | None = None, verboso: bool = False) -> str:
    hoy = (fecha or date.today()).isoformat()
    encargo = f"""Hoy es {hoy}. Investiga el estado de la flota y dime como esta.

Llama las herramientas que necesites. Cuando tengas suficiente, deja de
llamarlas y escribe tu diagnostico."""

    llm = obtener_llm().bind_tools(HERRAMIENTAS)
    mensajes = [SystemMessage(content=CONTEXTO), HumanMessage(content=encargo)]
    llamadas: list[str] = []

    for _ in range(MAX_VUELTAS):
        respuesta = llm.invoke(mensajes)
        mensajes.append(respuesta)
        if not respuesta.tool_calls:
            break
        for llamada in respuesta.tool_calls:
            llamadas.append(llamada["name"])
            argumentos = ", ".join(f"{k}={v}" for k, v in llamada["args"].items())
            print(f"  → {llamada['name']}({argumentos})")
            resultado = POR_NOMBRE[llamada["name"]].invoke(llamada["args"])
            mensajes.append(
                ToolMessage(str(resultado), tool_call_id=llamada["id"])
            )

    diagnostico = mensajes[-1].content
    print(f"\n{'─' * 68}\nDIAGNOSTICO\n{'─' * 68}")
    print(diagnostico)

    if verboso:
        print(f"\n{'─' * 68}\nHERRAMIENTAS LLAMADAS\n{'─' * 68}")
        print("  " + ", ".join(llamadas))

    return diagnostico


def main() -> None:
    p = argparse.ArgumentParser(prog="agente-plano", description=__doc__)
    p.add_argument("--fecha", type=date.fromisoformat, default=None)
    p.add_argument("--verboso", action="store_true")
    args = p.parse_args()
    correr(args.fecha, args.verboso)


if __name__ == "__main__":
    main()
