"""La interfaz del agente.

Dos pestañas y una idea. "La flota" muestra el problema: miles de filas donde
en algun lugar hay un modelo costando plata. "El agente" muestra como se
resuelve, y sobre todo COMO — paso a paso, con las herramientas que llamo, la
hipotesis que formulo, la critica que se hizo y la correccion si la hubo.

Un panel que solo mostrara el diagnostico final seria un tablero mas. Lo que
distingue a un agente es el razonamiento, asi que el razonamiento es lo que se
proyecta.
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

URL = os.getenv("URL_PLATAFORMA", "http://plataforma:8000")

st.set_page_config(page_title="Agente de monitoreo", page_icon="🛰️", layout="wide")
st.title("🛰️ Agente de monitoreo de modelos en produccion")
st.caption(
    "Taller 02 de caso aplicado de IA en industria · "
    "II Programa de Especializacion en IA Generativa y MLOps"
)

try:
    salud = httpx.get(f"{URL}/salud", timeout=15).json()
except Exception as exc:  # noqa: BLE001 — en clase queremos ver el error tal cual
    st.error(f"No se pudo contactar la plataforma en {URL}: {exc}")
    st.info("Levanta el entorno con:  make arriba && make seed")
    st.stop()

if not salud.get("filas_metricas"):
    st.warning("La plataforma responde pero no hay telemetria todavia.")
    st.info("Corre:  make seed")
    st.stop()

st.success(
    f"Entorno listo · {salud['modelos']} modelos en produccion · "
    f"{salud['filas_metricas']:,} dias-modelo de telemetria"
)


@st.cache_data(ttl=20)
def cargar_metricas() -> pd.DataFrame:
    df = pd.DataFrame(httpx.get(f"{URL}/v1/metricas", timeout=60).json())
    df["fecha"] = pd.to_datetime(df["fecha"])
    # La API tipa las columnas que conoce, pero un contenedor que lleva rato
    # levantado corre el codigo con el que arranco. Antes que reventar por una
    # columna que llego como texto, se convierte aca.
    for col in ("mape", "sesgo_pct", "cobertura", "unidades_reales",
                "unidades_pronosticadas"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


flota, agente_tab, memoria_tab, bitacora = st.tabs(
    ["La flota", "El agente", "Memoria", "Bitacora de acciones"]
)


# --------------------------------------------------------------------------
# La flota: el problema, antes de que exista el agente
# --------------------------------------------------------------------------

with flota:
    metricas = cargar_metricas()
    ultimos = metricas[
        metricas["fecha"] >= metricas["fecha"].max() - pd.Timedelta(days=13)
    ]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modelos", metricas["modelo_id"].nunique())
    c2.metric("MAPE medio", f"{ultimos['mape'].mean():.1f}%")
    # Cociente de totales, no promedio de porcentajes: el promedio de los
    # sesgos diarios esta sesgado hacia arriba. Ver _sesgo en herramientas.py.
    de_mas = ultimos["unidades_pronosticadas"].sum() - ultimos["unidades_reales"].sum()
    sesgo = de_mas / ultimos["unidades_reales"].sum() * 100
    c3.metric("Sesgo", f"{sesgo:+.1f}%", f"{de_mas:+,.0f} unidades")
    c4.metric("Cobertura", f"{ultimos['cobertura'].mean():.1%}")

    st.subheader("MAPE por categoria")
    st.line_chart(
        metricas.pivot_table(index="fecha", columns="categoria", values="mape"),
        height=280,
    )

    st.subheader("El problema")
    st.markdown(
        f"""
Esta tabla tiene **{len(metricas):,} filas**. Cada modelo aporta seis senales
distintas, todos los dias. En algun lugar de ahi dentro hay un modelo
degradandose y costando plata.

Encuentralo a mano. Te esperamos.
"""
    )
    st.dataframe(
        ultimos.sort_values("mape", ascending=False).head(25),
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------------
# El agente: el razonamiento, en vivo
# --------------------------------------------------------------------------

SEVERIDAD = {"alta": "🔴", "media": "🟠", "baja": "🟢"}
URGENCIA = {"inmediata": "🔴", "esta_semana": "🟠", "monitorear": "🔵"}


def _tarjeta_diagnostico(h: dict, corregido: bool) -> None:
    titulo = "Diagnostico" + (" · reescrito tras la reflexion" if corregido else "")
    st.subheader(titulo)
    st.markdown(f"### {h.get('titulo', '(sin titulo)')}")
    a, b, c = st.columns(3)
    a.metric("Tipo", h.get("tipo", "?"))
    b.metric("Alcance", h.get("alcance", "?"))
    c.metric("Severidad", f"{SEVERIDAD.get(h.get('severidad'), '')} {h.get('severidad', '?')}")
    if h.get("explicacion"):
        st.write(h["explicacion"])
    if h.get("evidencia"):
        st.markdown("**Evidencia**")
        for e in h["evidencia"]:
            st.markdown(f"- {e}")
    if h.get("impacto_negocio"):
        st.info(h["impacto_negocio"])


with agente_tab:
    proveedor = os.getenv("PROVEEDOR_LLM", "mock")
    modelo = os.getenv("MODELO_LLM", "(predeterminado del proveedor)")
    puede_actuar = os.getenv("EJECUTAR_ACCIONES", "").strip() in ("1", "true", "si")

    izq, der = st.columns([3, 2])
    izq.caption(f"Proveedor: **{proveedor}** · modelo: **{modelo}**")
    der.caption(
        "⚡ **puede reentrenar**" if puede_actuar
        else "🔒 solo diagnostico (EJECUTAR_ACCIONES=0)"
    )

    if proveedor == "mock":
        st.warning(
            "Estas con el modelo simulado: recorre el grafo entero pero no razona. "
            "Pon tu llave en `.env` para ver al agente pensar de verdad."
        )

    if st.button("Correr el agente", type="primary"):
        from agente.grafo import construir, estado_inicial

        grafo = construir()
        final = None
        herramientas_usadas: list[str] = []
        fases_vistas: set[str] = set()

        with st.status("Investigando la flota...", expanded=True) as tarea:
            for paso in grafo.stream(estado_inicial(), stream_mode="values"):
                final = paso

                mensajes = paso.get("mensajes") or []
                if mensajes:
                    for llamada in getattr(mensajes[-1], "tool_calls", []) or []:
                        args = ", ".join(f"{k}={v}" for k, v in llamada["args"].items())
                        st.write(f"🔍 `{llamada['name']}({args})`")
                        herramientas_usadas.append(llamada["name"])

                # Las fases se detectan por lo que el estado ya trae lleno.
                if paso.get("hipotesis") and "dx" not in fases_vistas:
                    fases_vistas.add("dx")
                    tarea.update(label="Formulando el diagnostico...")
                    st.write("🧠 Diagnostico formulado")
                if paso.get("critica") and "rf" not in fases_vistas:
                    fases_vistas.add("rf")
                    veredicto = paso["critica"].get("veredicto")
                    tarea.update(label="Cuestionando su propio diagnostico...")
                    st.write(f"🪞 Reflexion: **{veredicto}**")
                    if veredicto == "insuficiente":
                        st.write("✍️ La critica quedo en pie: reescribiendo el diagnostico")
                if paso.get("recomendaciones") and "rc" not in fases_vistas:
                    fases_vistas.add("rc")
                    tarea.update(label="Emitiendo recomendaciones...")
                    st.write("📋 Recomendaciones listas")

            tarea.update(label="Ejecucion completa", state="complete", expanded=False)

        if final is None:
            st.error("El grafo no produjo estado.")
            st.stop()

        critica = final.get("critica", {})
        corregido = critica.get("veredicto") == "insuficiente"

        _tarjeta_diagnostico(final.get("hipotesis", {}), corregido)

        st.subheader("Reflexion")
        st.caption(
            f"veredicto: **{critica.get('veredicto', '?')}** · "
            f"vueltas: {final.get('vueltas', 0)}"
        )
        objeciones = critica.get("objeciones") or []
        for o in objeciones:
            st.markdown(f"- {o}")
        if not objeciones:
            st.caption("No se puso ninguna objecion a si mismo.")
        if corregido:
            st.success("El diagnostico de arriba ya incorpora estas objeciones.")

        st.subheader("Recomendaciones")
        for r in final.get("recomendaciones", []):
            marca = URGENCIA.get(r.get("urgencia"), "·")
            with st.expander(
                f"{marca} **{r.get('accion')}** → {r.get('objetivo')}", expanded=True
            ):
                st.write(r.get("justificacion", ""))
                if r.get("resultado_esperado"):
                    st.caption(f"Resultado esperado: {r['resultado_esperado']}")

        acciones = final.get("acciones", [])
        if acciones:
            st.subheader("Accion")
            for a in acciones:
                if a.get("ejecutada"):
                    st.success(
                        f"✓ {a['accion']} → {a['objetivo']} · "
                        f"{a.get('modelos_reentrenados')} modelos en {a.get('duracion_s')}s"
                    )
                    continue
                st.warning(f"✗ No se ejecuto: {a.get('motivo', 'sin motivo')}")
                for d in a.get("habria_ejecutado", []):
                    st.caption(f"Habria reentrenado: {d.get('filtro') or 'la flota'}")

        if herramientas_usadas:
            st.caption("Herramientas llamadas: " + ", ".join(herramientas_usadas))


# --------------------------------------------------------------------------
# Memoria y bitacora
# --------------------------------------------------------------------------

with memoria_tab:
    from agente import memoria as mem

    st.markdown(
        "Sin memoria, el agente redescubre el mismo problema cada manana y emite "
        "la misma alerta. Con memoria puede decir tres cosas que un tablero nunca "
        "dice: *esto ya lo reporte*, *esto empeoro desde ayer*, *esto es nuevo*."
    )
    historial = mem.historial(20)
    if not historial:
        st.info("Todavia no hay diagnosticos guardados.")
    for d in historial:
        with st.expander(
            f"{SEVERIDAD.get(d.get('severidad'), '')} **{d['fecha']}** · {d['titulo']}"
        ):
            st.caption(f"alcance: {d.get('alcance', 'n/d')}")
            for e in d.get("evidencia", []):
                st.markdown(f"- {e}")


with bitacora:
    st.markdown(
        "Cada vez que el agente reentrena queda registrado: que modelos, cuando "
        "y con que motivo. Un agente que actua sin dejar rastro es un agente que "
        "nadie puede auditar."
    )
    try:
        registros = httpx.get(f"{URL}/v1/reentrenamientos", timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer la bitacora: {exc}")
        registros = []
    if not registros:
        st.info("Todavia no se ha reentrenado nada. Corre `make actuar`.")
    else:
        st.dataframe(
            pd.DataFrame(registros)[
                ["momento", "modelos", "alcance", "duracion_s", "motivo"]
            ],
            use_container_width=True,
            hide_index=True,
        )
