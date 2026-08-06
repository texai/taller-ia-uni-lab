"""Comprueba que el laboratorio hace lo que promete.

    python -m retos.verificar             # rapido, sin gastar tokens
    python -m retos.verificar --con-llm   # completo: corre el agente de verdad
    python -m retos.verificar --reto 2

Sirve para dos cosas. En clase, para que cada quien sepa si su implementacion
cumple sin esperar a que alguien se la revise. Y antes de clase, para saber en
un comando si el entorno esta sano — que es justo lo que uno quiere el sabado
a las 14:30 y no a las 15:05.

Las comprobaciones sin LLM son las que mas valen: verifican los datos y la
estadistica, que es donde estuvieron casi todos los errores de verdad.
"""

from __future__ import annotations

import argparse
import sys

VERDE, ROJO, GRIS, FIN = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


class Resultado:
    def __init__(self) -> None:
        self.fallos: list[str] = []
        self.total = 0

    def check(self, condicion: bool, descripcion: str, detalle: str = "") -> bool:
        self.total += 1
        if condicion:
            print(f"  {VERDE}✓{FIN} {descripcion}")
        else:
            print(f"  {ROJO}✗{FIN} {descripcion}")
            if detalle:
                print(f"    {GRIS}{detalle}{FIN}")
            self.fallos.append(descripcion)
        return condicion


def _mundo(escenario: str | None) -> None:
    """Deja el mundo en el estado pedido. Determinista: mismos datos siempre.

    Va por HTTP y no por la linea de comandos porque el verificador corre en
    el contenedor del agente, que a proposito no tiene acceso al codigo de la
    plataforma ni a su disco. El agente ve lo mismo que veria en produccion.
    """
    import httpx

    from agente.herramientas import URL

    r = httpx.post(
        f"{URL}/v1/laboratorio/mundo", json={"escenario": escenario}, timeout=300
    )
    r.raise_for_status()


# --------------------------------------------------------------------------


def reto_1(r: Resultado) -> None:
    """La plataforma responde y hay telemetria que mirar."""
    print("\nReto 1 · el mundo esta en pie")
    from agente.herramientas import _get

    salud = _get("/salud")
    r.check(salud.get("modelos") == 192, "192 modelos en produccion",
            f"encontrados: {salud.get('modelos')}")
    r.check(salud.get("filas_metricas", 0) > 15000, "hay telemetria suficiente",
            f"filas: {salud.get('filas_metricas')}. Corre: make seed")


def reto_2(r: Resultado) -> None:
    """Las herramientas de percepcion separan senal de ruido.

    Este es el criterio que de verdad importa: en un mundo sano no puede
    encenderse ninguna bandera. Un detector que alarma sobre lo normal no
    sirve para nada, y ningun agente construido encima puede arreglarlo.
    """
    print("\nReto 2 · percepcion")
    from agente.herramientas import comparar_periodos, detectar_anomalias, resumen_flota

    _mundo(None)
    encendidas = []
    for dim in ("categoria", "tienda", "region"):
        c = comparar_periodos.invoke(
            {"dias_recientes": 14, "dias_base": 45, "dimension": dim}
        )
        res = c["resumen"]
        encendidas += res["con_deriva_de_error"] + res["con_deriva_de_sesgo"]
    r.check(not encendidas, "la flota sana no enciende ninguna bandera",
            f"encendidas: {encendidas}")

    g = resumen_flota.invoke({"dias": 14})["global"]
    r.check(abs(g["sesgo_pct"]) < 2.0, "el sesgo de una flota sana ronda cero",
            f"sesgo: {g['sesgo_pct']}%. Cuidado con promediar porcentajes.")
    r.check(detectar_anomalias.invoke({"dias": 21})["n_anomalias"] == 0,
            "no hay anomalias donde no las hay")

    _mundo("campana_promocional")
    c = comparar_periodos.invoke(
        {"dias_recientes": 14, "dias_base": 45, "dimension": "categoria"}
    )["resumen"]
    r.check(c["con_deriva_de_error"] == ["bebidas"],
            "la campana promocional se ve, y solo en bebidas",
            f"marcadas: {c['con_deriva_de_error']}")

    _mundo("sesgo_silencioso")
    c = comparar_periodos.invoke(
        {"dias_recientes": 14, "dias_base": 45, "dimension": "categoria"}
    )["resumen"]
    r.check(len(c["con_deriva_de_sesgo"]) == 8,
            "el sesgo silencioso aparece en las 8 categorias",
            f"marcadas: {len(c['con_deriva_de_sesgo'])} de 8")
    r.check(len(c["con_deriva_de_error"]) <= 2,
            "y el MAPE casi no se entera (por eso es silencioso)",
            f"categorias con deriva de error: {c['con_deriva_de_error']}")

    _mundo("feed_caido")
    a = detectar_anomalias.invoke({"dias": 21})
    tiendas = [h.get("tienda") for h in a["anomalias"]]
    r.check("arequipa" in tiendas, "la tienda muda se detecta como anomalia",
            f"anomalias: {a['anomalias']}")
    c = comparar_periodos.invoke(
        {"dias_recientes": 14, "dias_base": 45, "dimension": "categoria"}
    )["resumen"]
    r.check(not c["con_deriva_de_error"] and not c["con_deriva_de_sesgo"],
            "y NO se confunde con deriva: la flota se ve sana")


def reto_3(r: Resultado) -> None:
    """Hay un modelo configurado y responde."""
    print("\nReto 3 · el modelo responde")
    import os

    from agente.herramientas import HERRAMIENTAS
    from agente.llm import obtener_llm

    proveedor = os.getenv("PROVEEDOR_LLM", "mock")
    r.check(len(HERRAMIENTAS) >= 5, f"{len(HERRAMIENTAS)} herramientas expuestas")
    if proveedor == "mock":
        print(f"  {GRIS}· proveedor mock: no se comprueba el razonamiento{FIN}")
        return
    try:
        respuesta = obtener_llm().bind_tools(HERRAMIENTAS).invoke(
            "Llama resumen_flota para ver como va la flota."
        )
        r.check(bool(getattr(respuesta, "tool_calls", None)),
                f"{proveedor} responde y sabe llamar herramientas")
    except Exception as e:  # noqa: BLE001
        r.check(False, f"{proveedor} responde", str(e)[:200])


def reto_4(r: Resultado, con_llm: bool) -> None:
    """El grafo esta cableado y lee cada mundo distinto."""
    print("\nReto 4 · arquitectura cognitiva")
    from agente.grafo import construir

    nodos = set(construir().get_graph().nodes)
    for n in ("percepcion", "herramientas", "diagnostico", "reflexion",
              "revision", "recomendacion", "accion"):
        r.check(n in nodos, f"el grafo tiene el nodo '{n}'")

    if not con_llm:
        print(f"  {GRIS}· los diagnosticos se comprueban con --con-llm{FIN}")
        return

    from agente import memoria
    from agente.grafo import estado_inicial

    esperado = {
        None: "sin_hallazgos",
        "sesgo_silencioso": "deriva",
        "feed_caido": "anomalia",
    }
    for escenario, tipo in esperado.items():
        _mundo(escenario)
        memoria.limpiar()  # sin memoria previa: cada mundo se juzga solo
        final = None
        for paso in construir().stream(estado_inicial(), stream_mode="values"):
            final = paso
        h = (final or {}).get("hipotesis", {})
        nombre = escenario or "mundo sano"
        r.check(h.get("tipo") == tipo, f"{nombre} → diagnostica '{tipo}'",
                f"dijo: '{h.get('tipo')}' — {h.get('titulo', '')[:90]}")


def reto_5(r: Resultado) -> None:
    """La politica de accion frena lo que debe frenar."""
    print("\nReto 5 · accion y frenos")
    from agente.accion import evaluar

    categoria = {
        "accion": "reentrenar", "objetivo": "panaderia",
        "objetivo_tipo": "categoria", "objetivo_valor": "panaderia",
        "urgencia": "esta_semana",
    }
    flota = {
        "accion": "reentrenar", "objetivo": "todo",
        "objetivo_tipo": "flota", "urgencia": "inmediata",
    }
    revisar = {
        "accion": "revisar_datos", "objetivo": "feed",
        "objetivo_tipo": "tienda", "objetivo_valor": "arequipa",
        "urgencia": "inmediata",
    }

    def ejecutables(tipo: str, recs: list[dict]) -> int:
        return sum(
            bool(d.get("ejecutable"))
            for d in evaluar({"tipo": tipo, "titulo": "t"}, recs)
        )

    r.check(ejecutables("deriva", [categoria]) == 1,
            "con deriva, reentrenar una categoria se ejecuta")
    r.check(ejecutables("anomalia", [categoria]) == 0,
            "con anomalia NO se reentrena: el feed esta roto")
    r.check(ejecutables("deriva", [flota]) == 0,
            "reentrenar la flota entera necesita una persona")
    r.check(ejecutables("deriva", [revisar]) == 0,
            "revisar_datos no se automatiza: termina en un humano")

    from agente.herramientas import _get

    _get("/v1/reentrenamientos")
    r.check(True, "la bitacora de reentrenamientos responde")


# --------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(prog="retos.verificar", description=__doc__)
    p.add_argument("--reto", type=int, choices=[1, 2, 3, 4, 5])
    p.add_argument("--con-llm", action="store_true",
                   help="corre el agente de verdad (tarda unos minutos y gasta tokens)")
    args = p.parse_args()

    r = Resultado()
    pendientes = [args.reto] if args.reto else [1, 2, 3, 4, 5]
    try:
        if 1 in pendientes:
            reto_1(r)
        if 2 in pendientes:
            reto_2(r)
        if 3 in pendientes:
            reto_3(r)
        if 4 in pendientes:
            reto_4(r, args.con_llm)
        if 5 in pendientes:
            reto_5(r)
    except Exception as e:  # noqa: BLE001
        print(f"\n{ROJO}La verificacion se cayo: {type(e).__name__}: {e}{FIN}")
        if "404" in str(e):
            # Sintoma clasico: el contenedor lleva rato arriba y sirve el
            # codigo con el que arranco, no el que acabas de traer.
            print("Un 404 en una ruta que existe suele ser una plataforma vieja.")
            print("Reiniciala:  make abajo && make arriba")
        else:
            print("¿Esta levantado el entorno?  make arriba && make seed")
        sys.exit(2)

    # Las comprobaciones degradan el mundo a proposito, y la ultima lo deja
    # roto. Devolverlo sano es parte del trabajo: nadie quiere descubrir a las
    # 15:05 que la clase arranco con una tienda muda.
    if any(x in pendientes for x in (2, 4)):
        print(f"\n{GRIS}Dejando el mundo sano otra vez...{FIN}")
        _mundo(None)

    print()
    if r.fallos:
        print(f"{ROJO}{len(r.fallos)} de {r.total} comprobaciones fallaron:{FIN}")
        for f in r.fallos:
            print(f"  · {f}")
        sys.exit(1)
    print(f"{VERDE}Las {r.total} comprobaciones pasaron.{FIN}")


if __name__ == "__main__":
    main()
