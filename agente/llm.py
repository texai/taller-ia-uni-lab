"""Seleccion del modelo de lenguaje, agnostica al proveedor.

Cada participante trae su propia llave y no todas son del mismo proveedor. Este
modulo aisla esa diferencia: el resto del agente pide `obtener_llm()` y no sabe
ni le importa quien esta detras.

`mock` devuelve un modelo determinista, sin red. No sirve para aprender como
razona un LLM, pero sirve para que nadie se quede trabado en clase por una llave
vencida o una cuota agotada.
"""

from __future__ import annotations

import json
import os

PREDETERMINADOS = {
    "google": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "qwen2.5:3b-instruct",
    "mock": "mock",
}


def obtener_llm(temperatura: float = 0.0):
    proveedor = os.getenv("PROVEEDOR_LLM", "mock").strip().lower()
    modelo = os.getenv("MODELO_LLM") or PREDETERMINADOS.get(proveedor, "")

    if proveedor == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=modelo, temperature=temperatura)

    if proveedor == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=modelo, temperature=temperatura)

    if proveedor == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=modelo, temperature=temperatura)

    if proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=modelo, temperature=temperatura)

    if proveedor == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=modelo,
            temperature=temperatura,
            base_url=os.getenv("URL_OLLAMA", "http://ollama:11434"),
        )

    if proveedor == "mock":
        return _LLMSimulado()

    raise ValueError(
        f"PROVEEDOR_LLM desconocido: {proveedor!r}. "
        f"Opciones: {', '.join(PREDETERMINADOS)}"
    )


class _LLMSimulado:
    """Un modelo de mentira que igual recorre el grafo entero.

    No razona: reconoce por la forma del pedido en que nodo esta y devuelve
    una respuesta con la estructura correcta. Llama una herramienta de verdad
    y devuelve JSON valido, asi que sirve para dos cosas: que nadie se quede
    trabado sin llave, y que un error de cableado del grafo aparezca aca en
    vez de aparecer recien cuando alguien gasta tokens.

    Un simulador que nunca falla no verifica nada.
    """

    def __init__(self, con_herramientas: bool = False):
        self._con_herramientas = con_herramientas

    def bind_tools(self, *_args, **_kwargs):
        return _LLMSimulado(con_herramientas=True)

    def invoke(self, mensajes, **_):
        from langchain_core.messages import AIMessage, ToolMessage

        nota = "[modelo simulado: no hay LLM configurado, revisa PROVEEDOR_LLM]"
        pedido = ""
        if mensajes:
            contenido = getattr(mensajes[-1], "content", "")
            pedido = contenido if isinstance(contenido, str) else str(contenido)

        # Percepcion. Primero pide datos; despues de recibirlos, concluye.
        if self._con_herramientas:
            ya_miro = any(isinstance(m, ToolMessage) for m in mensajes)
            if not ya_miro:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "resumen_flota",
                            "args": {"dias": 14},
                            "id": "simulada-1",
                        }
                    ],
                )
            return AIMessage(content=f"{nota} Revise el resumen de la flota.")

        # Los demas nodos se reconocen por la forma del JSON que piden.
        if '"veredicto"' in pedido:
            return AIMessage(
                content=json.dumps(
                    {
                        "veredicto": "confirmado",
                        "objeciones": [f"{nota} sin critica real"],
                        "que_falta_mirar": "",
                    }
                )
            )
        if '"recomendaciones"' in pedido:
            return AIMessage(
                content=json.dumps(
                    {
                        "recomendaciones": [
                            {
                                "accion": "ninguna",
                                "objetivo": "flota",
                                "urgencia": "monitorear",
                                "justificacion": nota,
                                "resultado_esperado": "n/d",
                            }
                        ]
                    }
                )
            )
        return AIMessage(
            content=json.dumps(
                {
                    "titulo": f"{nota} sin diagnostico real",
                    "tipo": "sin_hallazgos",
                    "alcance": "flota",
                    "severidad": "baja",
                    "explicacion": "Configura una llave para que el agente razone.",
                    "evidencia": [],
                    "impacto_negocio": "n/d",
                }
            )
        )
