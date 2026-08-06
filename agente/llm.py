"""Seleccion del modelo de lenguaje, agnostica al proveedor.

Cada participante trae su propia llave y no todas son del mismo proveedor. Este
modulo aisla esa diferencia: el resto del agente pide `obtener_llm()` y no sabe
ni le importa quien esta detras.

`mock` devuelve un modelo determinista, sin red. No sirve para aprender como
razona un LLM, pero sirve para que nadie se quede trabado en clase por una llave
vencida o una cuota agotada.
"""

from __future__ import annotations

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
    """Respuestas fijas, para no bloquear a nadie."""

    def invoke(self, mensajes, **_):
        from langchain_core.messages import AIMessage

        return AIMessage(
            content=(
                "[modelo simulado] No hay LLM configurado. "
                "Revisa PROVEEDOR_LLM y la llave en tu archivo .env."
            )
        )

    def bind_tools(self, *_args, **_kwargs):
        return self
