"""La arquitectura cognitiva del agente, como grafo de LangGraph.

    percepcion  ->  diagnostico  ->  reflexion  ->  recomendacion
         ^                              |
         +---------- (una vuelta) ------+

Cada nodo tiene un trabajo y solo uno:

- **percepcion**: decide que mirar y llama herramientas hasta tener evidencia.
  No concluye nada.
- **diagnostico**: convierte la evidencia en una hipotesis, con alcance
  (un modelo / una categoria / una tienda / la flota) y severidad.
- **reflexion**: intenta refutar la hipotesis. Si la evidencia no la sostiene,
  devuelve el control a percepcion UNA vez para buscar lo que falta.
- **recomendacion**: emite acciones concretas y accionables.

La reflexion es lo que separa a este agente de un dashboard con umbrales:
antes de alertar, se cuestiona a si mismo.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agente import memoria
from agente.herramientas import HERRAMIENTAS
from agente.llm import obtener_llm

MAX_VUELTAS = 2


class Estado(TypedDict):
    fecha: str
    mensajes: Annotated[list[AnyMessage], add_messages]
    evidencia: list[str]
    hipotesis: dict[str, Any]
    critica: dict[str, Any]
    recomendaciones: list[dict[str, Any]]
    vueltas: int


CONTEXTO = """Eres el agente de guardia de una cadena de retail con 24 tiendas
y 8 categorias. En produccion hay 192 modelos de pronostico de demanda, uno
por tienda y categoria. Un job batch corre cada madrugada y proyecta 14 dias.

Tu trabajo es vigilar esa flota. Nadie puede revisar 192 modelos a mano.

Lo que debes tener presente:

- El MAPE y el sesgo dicen cosas distintas. El MAPE mide cuanto se equivoca
  el modelo; el sesgo, hacia que lado. Un sesgo positivo sostenido significa
  sobre-pronostico, y sobre-pronostico significa sobre-stock: plata inmovilizada
  en almacen. Un modelo con MAPE estable y sesgo creciente esta costando dinero
  sin disparar ninguna alerta de umbral.
- Deriva y anomalia no son lo mismo. La deriva es el mundo cambiando y el
  modelo quedandose atras: se corrige reentrenando. Una anomalia es algo roto
  (un feed caido, un job que no corrio): reentrenar ahi no arregla nada y
  ademas contamina el modelo con datos malos.
- La forma del problema importa mas que su tamano. Si la degradacion aparece
  en una categoria a lo largo de todas las tiendas, la causa es del producto.
  Si aparece en una tienda a lo largo de todas las categorias, la causa es de
  esa tienda. Y si aparece en TODAS, la causa no es de ninguna: es de la
  cadena, y el alcance correcto es la flota entera.
- Un nivel no es un cambio. Que una categoria tenga 6% de sesgo no dice nada
  por si solo: puede llevar asi todo el año. Lo que importa es cuanto se
  movio contra su linea base.
- Las herramientas ya descartaron el ruido por ti. Toda la flota pierde algo
  de precision con las semanas, asi que un delta abultado SIN su bandera
  encendida es envejecimiento normal, ya evaluado y descartado: no lo cites
  como evidencia de deriva. Y no ordenes tus hallazgos por el delta de MAPE;
  el MAPE es la senal ruidosa. Ordenalos por lo que las banderas digan.
- Si ninguna bandera se encendio y no hay anomalias, el diagnostico correcto
  es "sin_hallazgos". Una guardia tranquila es un resultado, no un fracaso.
"""


def _texto(respuesta) -> str:
    contenido = respuesta.content
    if isinstance(contenido, str):
        return contenido
    return " ".join(
        bloque.get("text", "") for bloque in contenido if isinstance(bloque, dict)
    )


def _json_de(respuesta, por_defecto: dict) -> dict:
    """Extrae el primer objeto JSON de la respuesta. Los modelos pequenos a
    veces lo envuelven en prosa o en un bloque de codigo."""
    txt = _texto(respuesta).strip()
    if "```" in txt:
        txt = txt.split("```")[1].removeprefix("json").strip()
    inicio, fin = txt.find("{"), txt.rfind("}")
    if inicio == -1 or fin == -1:
        return por_defecto
    try:
        return json.loads(txt[inicio : fin + 1])
    except json.JSONDecodeError:
        return por_defecto


# --------------------------------------------------------------------------
# Nodos
# --------------------------------------------------------------------------


def percepcion(estado: Estado) -> dict:
    """Decide que mirar y llama herramientas. No concluye."""
    llm = obtener_llm().bind_tools(HERRAMIENTAS)

    if not estado["mensajes"]:
        # El system dice QUIEN eres; el turno humano, QUE te pido hoy. No es
        # cosmetico: Anthropic manda el system en un parametro aparte de la
        # peticion, asi que una conversacion de puro SystemMessage le llega con
        # la lista de mensajes vacia y la API la rechaza.
        encargo = f"""{memoria.resumen_para_prompt()}

Hoy es {estado['fecha']}. Investiga el estado de la flota.

Empieza por el panorama general y despues profundiza donde veas algo raro.
Contrasta siempre lo reciente contra una linea base: un numero suelto no dice
nada sin su historia. Antes de concluir que un modelo se degrado, descarta que
el problema sea de datos o del job.

Llama las herramientas que necesites. Cuando tengas evidencia suficiente para
sostener una conclusion, deja de llamar herramientas y resume lo que
encontraste en texto plano."""
        apertura = [SystemMessage(content=CONTEXTO), HumanMessage(content=encargo)]
    else:
        apertura = []

    mensajes = estado["mensajes"] + apertura
    respuesta = llm.invoke(mensajes)
    # La apertura viaja de vuelta al estado. Si no, al volver aca despues de
    # llamar una herramienta el agente habria perdido su contexto y su encargo,
    # y estaria razonando a ciegas sobre una lista de resultados sueltos.
    return {"mensajes": apertura + [respuesta]}


def _hay_herramientas(estado: Estado) -> Literal["herramientas", "diagnostico"]:
    ultimo = estado["mensajes"][-1]
    if getattr(ultimo, "tool_calls", None):
        return "herramientas"
    return "diagnostico"


def diagnostico(estado: Estado) -> dict:
    """Convierte la evidencia en una hipotesis con alcance y severidad."""
    llm = obtener_llm()
    peticion = HumanMessage(
        content="""Formula tu diagnostico a partir de lo que investigaste.

Responde SOLO con un objeto JSON:

{
  "titulo": "una linea que resuma el problema",
  "tipo": "deriva | anomalia | sin_hallazgos",
  "alcance": "flota | categoria:<nombre> | tienda:<nombre> | modelo:<id>",
  "severidad": "alta | media | baja",
  "explicacion": "por que crees esto, en dos o tres frases",
  "evidencia": ["numero concreto que lo sostiene", "otro numero"],
  "impacto_negocio": "que le cuesta esto a la cadena, en lenguaje de negocio"
}

Si no encontraste nada anomalo, usa tipo "sin_hallazgos" y dilo sin adornos.
No inventes un problema para tener algo que reportar."""
    )
    respuesta = llm.invoke(estado["mensajes"] + [peticion])
    hipotesis = _json_de(
        respuesta,
        {
            "titulo": "Diagnostico no estructurado",
            "tipo": "sin_hallazgos",
            "alcance": "flota",
            "severidad": "baja",
            "explicacion": _texto(respuesta)[:500],
            "evidencia": [],
            "impacto_negocio": "n/d",
        },
    )
    return {
        "hipotesis": hipotesis,
        "evidencia": hipotesis.get("evidencia", []),
        "mensajes": [peticion, respuesta],
    }


def reflexion(estado: Estado) -> dict:
    """Intenta refutar la propia hipotesis antes de emitirla."""
    llm = obtener_llm()
    peticion = HumanMessage(
        content=f"""Ahora critica tu propio diagnostico. Se exigente contigo mismo.

Diagnostico a revisar:
{json.dumps(estado['hipotesis'], ensure_ascii=False, indent=2)}

Preguntate:
- La evidencia que citas, ¿sostiene de verdad esta conclusion, o la estas
  forzando?
- ¿Confundiste una anomalia de datos con una deriva del modelo?
- El alcance que declaraste, ¿es el correcto? ¿Miraste si el patron aparece
  tambien en otras categorias, tiendas o regiones?
- ¿Hay alguna herramienta que no llamaste y que cambiaria la conclusion?

Responde SOLO con JSON:

{{
  "veredicto": "confirmado | insuficiente",
  "objeciones": ["objecion concreta", "otra"],
  "que_falta_mirar": "si el veredicto es insuficiente, que herramienta llamar y por que"
}}

Usa "insuficiente" solo si falta evidencia que cambiaria la conclusion, no por
prurito. Si el diagnostico se sostiene, confirmalo."""
    )
    respuesta = llm.invoke(estado["mensajes"] + [peticion])
    critica = _json_de(
        respuesta, {"veredicto": "confirmado", "objeciones": [], "que_falta_mirar": ""}
    )
    return {
        "critica": critica,
        "vueltas": estado.get("vueltas", 0) + 1,
        "mensajes": [peticion, respuesta],
    }


def _tras_reflexion(estado: Estado) -> Literal["percepcion", "recomendacion"]:
    insuficiente = estado["critica"].get("veredicto") == "insuficiente"
    if insuficiente and estado.get("vueltas", 0) < MAX_VUELTAS:
        return "percepcion"
    return "recomendacion"


def recomendacion(estado: Estado) -> dict:
    """Emite acciones concretas."""
    llm = obtener_llm()
    peticion = HumanMessage(
        content="""Emite tus recomendaciones. Responde SOLO con JSON:

{
  "recomendaciones": [
    {
      "accion": "reentrenar | revisar_datos | investigar | ninguna",
      "objetivo": "modelo, categoria o tienda sobre la que actuar",
      "urgencia": "inmediata | esta_semana | monitorear",
      "justificacion": "una frase",
      "resultado_esperado": "que deberia cambiar si esto funciona"
    }
  ]
}

Reglas:
- Si el problema es de datos, NO recomiendes reentrenar: reentrenar con datos
  malos empeora el modelo.
- Si no hay hallazgos, devuelve una sola recomendacion con accion "ninguna".
- Se especifico en el objetivo. "Revisar los modelos" no es accionable;
  "reentrenar los 24 modelos de la categoria bebidas" si lo es."""
    )
    respuesta = llm.invoke(estado["mensajes"] + [peticion])
    datos = _json_de(respuesta, {"recomendaciones": []})
    recomendaciones = datos.get("recomendaciones") or []
    if not recomendaciones:
        # Terminar en silencio es la peor salida posible: el turno de guardia
        # cierra sin decir que hacer y nadie sabe si es que no hay nada o si
        # es que el agente se cayo.
        recomendaciones = [
            {
                "accion": "investigar",
                "objetivo": estado["hipotesis"].get("alcance", "flota"),
                "urgencia": "monitorear",
                "justificacion": (
                    "El agente no logro emitir recomendaciones estructuradas "
                    "para este diagnostico. Revisar a mano."
                ),
                "resultado_esperado": "n/d",
            }
        ]
    return {
        "recomendaciones": recomendaciones,
        "mensajes": [peticion, respuesta],
    }


# --------------------------------------------------------------------------
# Construccion del grafo
# --------------------------------------------------------------------------


def construir():
    g = StateGraph(Estado)
    g.add_node("percepcion", percepcion)
    # ToolNode lee y escribe en la clave "messages" por omision. Nuestro estado
    # la llama "mensajes", asi que hay que decirselo o no encuentra la llamada.
    g.add_node("herramientas", ToolNode(HERRAMIENTAS, messages_key="mensajes"))
    g.add_node("diagnostico", diagnostico)
    g.add_node("reflexion", reflexion)
    g.add_node("recomendacion", recomendacion)

    g.add_edge(START, "percepcion")
    g.add_conditional_edges("percepcion", _hay_herramientas)
    g.add_edge("herramientas", "percepcion")
    g.add_edge("diagnostico", "reflexion")
    g.add_conditional_edges("reflexion", _tras_reflexion)
    g.add_edge("recomendacion", END)

    return g.compile()


def estado_inicial(fecha: date | None = None) -> Estado:
    return {
        "fecha": (fecha or date.today()).isoformat(),
        "mensajes": [],
        "evidencia": [],
        "hipotesis": {},
        "critica": {},
        "recomendaciones": [],
        "vueltas": 0,
    }
