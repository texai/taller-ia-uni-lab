"""Interfaz del agente.

El panel completo — ejecucion paso a paso, diagnostico y recomendaciones — se
construye durante la sesion 2. Lo que ves ahora sirve para dos cosas: verificar
que tu entorno quedo bien antes del sabado, y mostrar el problema que da origen
al taller.
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

metricas = pd.DataFrame(httpx.get(f"{URL}/v1/metricas", timeout=60).json())
metricas["fecha"] = pd.to_datetime(metricas["fecha"])
# La API tipa las columnas que conoce, pero un contenedor que lleva rato
# levantado corre el codigo con el que arranco. Antes que reventar por una
# columna que llego como texto, se convierte aca.
for col in ("mape", "sesgo_pct", "cobertura", "unidades_reales", "unidades_pronosticadas"):
    if col in metricas:
        metricas[col] = pd.to_numeric(metricas[col], errors="coerce")

ultimos = metricas[metricas["fecha"] >= metricas["fecha"].max() - pd.Timedelta(days=13)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Modelos", metricas["modelo_id"].nunique())
c2.metric("MAPE medio", f"{ultimos['mape'].mean():.1f}%")
# Cociente de totales, no promedio de porcentajes: ver _sesgo en herramientas.
_sesgo_flota = (
    ultimos["unidades_pronosticadas"].sum() / ultimos["unidades_reales"].sum() - 1
) * 100
c3.metric("Sesgo", f"{_sesgo_flota:+.1f}%")
c4.metric("Cobertura", f"{ultimos['cobertura'].mean():.1%}")

st.subheader("MAPE por categoria")
st.line_chart(
    metricas.pivot_table(index="fecha", columns="categoria", values="mape"),
    height=300,
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
