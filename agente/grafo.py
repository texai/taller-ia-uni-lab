"""La arquitectura cognitiva del agente, como grafo de LangGraph.

    percepcion -> diagnostico -> reflexion -> recomendacion -> accion
         ^                          |   |          ^
         +---- (falta evidencia) ---+   |          |
                                        +-> revision
                                    (la critica quedo en pie)

Cada nodo tiene un trabajo y solo uno:

- **percepcion**: decide que mirar y llama herramientas hasta tener evidencia.
  No concluye nada.
- **diagnostico**: convierte la evidencia en una hipotesis, con alcance
  (un modelo / una categoria / una tienda / la flota) y severidad.
- **reflexion**: intenta refutar la hipotesis. Si le falta evidencia, devuelve
  el control a percepcion para buscarla.
- **revision**: si la critica sigue en pie y ya no quedan vueltas, reescribe
  el diagnostico haciendose cargo de ella.
- **recomendacion**: emite acciones concretas y accionables.
- **accion**: ejecuta las que una politica de codigo deja pasar. Sin LLM: ver
  `agente/accion.py`.

La reflexion es lo que separa a este agente de un dashboard con umbrales:
antes de alertar, se cuestiona a si mismo. Pero cuestionarse sin poder
corregirse no sirve de nada -- el diagnostico saldria contradiciendo a sus
propias recomendaciones -- y por eso existe revision.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agente import memoria
from agente.accion import evaluar, ejecutar
from agente.herramientas import HERRAMIENTAS
from agente.llm import obtener_llm

MAX_VUELTAS = 2

# Actuar esta apagado por omision. Un agente que reentrena solo la primera vez
# que alguien lo corre es una sorpresa desagradable; que haya que encenderlo a
# mano es parte de la leccion.
EJECUTAR_ACCIONES = os.getenv("EJECUTAR_ACCIONES", "").strip() in ("1", "true", "si")


class Estado(TypedDict):
    fecha: str
    mensajes: Annotated[list[AnyMessage], add_messages]
    evidencia: list[str]
    hipotesis: dict[str, Any]
    critica: dict[str, Any]
    recomendaciones: list[dict[str, Any]]
    acciones: list[dict[str, Any]]
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
  Pero al reves vale igual: si las banderas SI se encendieron, hay hallazgo,
  y punto. Los umbrales ya hicieron el trabajo de separar senal de ruido; no
  pidas mas datos para creerles. No saber por que ocurrio algo no es lo mismo
  que no saber si ocurrio: puedes reportar una deriva confirmada y dejar su
  causa abierta. Callartela porque te falta la explicacion es el error caro.
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


def _tras_reflexion(estado: Estado) -> Literal["percepcion", "revision", "recomendacion"]:
    if estado["critica"].get("veredicto") != "insuficiente":
        return "recomendacion"
    # Todavia quedan vueltas: falta mirar algo, se vuelve a percibir.
    if estado.get("vueltas", 0) < MAX_VUELTAS:
        return "percepcion"
    # Se acabaron las vueltas y la critica sigue en pie. Emitir igual el
    # diagnostico que la critica acaba de demoler seria absurdo: la reflexion
    # podria objetar pero nunca enmendar, y el titular quedaria contradiciendo
    # a las recomendaciones que salen abajo.
    return "revision"


def revision(estado: Estado) -> dict:
    """Reescribe el diagnostico haciendose cargo de sus propias objeciones."""
    llm = obtener_llm()
    peticion = HumanMessage(
        content=f"""Tu propia critica dejo tu diagnostico en pie de guerra.

Diagnostico emitido:
{json.dumps(estado['hipotesis'], ensure_ascii=False, indent=2)}

Objeciones que le hiciste:
{json.dumps(estado['critica'].get('objeciones', []), ensure_ascii=False, indent=2)}

Reescribelo haciendote cargo de ellas. Ya no vas a mirar mas evidencia: con
la que tienes alcanza, y es la misma que sostiene tus objeciones.

- Si la critica dice que declaraste "sin_hallazgos" habiendo hallazgos,
  corrige el tipo. Que no sepas la causa ultima no significa que no haya nada:
  una deriva confirmada es un hallazgo aunque su origen quede abierto.
- Si dice que el alcance estaba mal, corrigelo. Si una senal aparece en todos
  los grupos, el alcance es la flota.
- Si dice que exageraste, baja la severidad.

Responde SOLO con el JSON del diagnostico, en el mismo formato de antes."""
    )
    respuesta = llm.invoke(estado["mensajes"] + [peticion])
    return {
        "hipotesis": _json_de(respuesta, estado["hipotesis"]),
        "mensajes": [peticion, respuesta],
    }


def recomendacion(estado: Estado) -> dict:
    """Emite acciones concretas."""
    llm = obtener_llm()
    peticion = HumanMessage(
        content="""Emite tus recomendaciones. Responde SOLO con JSON:

{
  "recomendaciones": [
    {
      "accion": "reentrenar | revisar_datos | investigar | ninguna",
      "objetivo": "en palabras: sobre que actuar",
      "objetivo_tipo": "categoria | tienda | modelo_id | flota",
      "objetivo_valor": "el nombre exacto, tal como aparece en la telemetria (vacio si es flota)",
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
  "reentrenar los 24 modelos de la categoria bebidas" si lo es.
- `objetivo_tipo` y `objetivo_valor` se ejecutan tal cual: son el filtro con
  el que la plataforma va a buscar los modelos. Usa nombres exactos de la
  telemetria ("panaderia", "arequipa", "dem-panaderia-callao"), no
  descripciones. Lo que marques como "inmediata" y "reentrenar" se dispara
  de verdad."""
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


def accion(estado: Estado) -> dict:
    """Ejecuta lo que la politica deja pasar. Sin LLM de por medio."""
    if not EJECUTAR_ACCIONES:
        return {"acciones": [_sin_ejecutar_todo(estado)]}
    return {"acciones": ejecutar(estado["hipotesis"], estado["recomendaciones"])}


def _sin_ejecutar_todo(estado: Estado) -> dict:
    return {
        "ejecutada": False,
        "motivo": (
            "modo solo-diagnostico: pon EJECUTAR_ACCIONES=1 para que el agente "
            "dispare de verdad el reentrenamiento"
        ),
        "habria_ejecutado": [
            d for d in evaluar(estado["hipotesis"], estado["recomendaciones"])
            if d.get("ejecutable")
        ],
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
    g.add_node("revision", revision)
    g.add_node("recomendacion", recomendacion)
    g.add_node("accion", accion)

    g.add_edge(START, "percepcion")
    g.add_conditional_edges("percepcion", _hay_herramientas)
    g.add_edge("herramientas", "percepcion")
    g.add_edge("diagnostico", "reflexion")
    g.add_conditional_edges("reflexion", _tras_reflexion)
    g.add_edge("revision", "recomendacion")
    g.add_edge("recomendacion", "accion")
    g.add_edge("accion", END)

    return g.compile()


def estado_inicial(fecha: date | None = None) -> Estado:
    return {
        "fecha": (fecha or date.today()).isoformat(),
        "mensajes": [],
        "evidencia": [],
        "hipotesis": {},
        "critica": {},
        "recomendaciones": [],
        "acciones": [],
        "vueltas": 0,
    }
