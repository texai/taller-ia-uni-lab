"""Ejecuta el agente.

    python -m agente run                      # una corrida
    python -m agente run --fecha 2026-08-08
    python -m agente memoria                  # que recuerda
    python -m agente memoria --limpiar
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from agente import memoria
from agente.grafo import construir, estado_inicial


def _linea(titulo: str) -> None:
    print(f"\n{'─' * 68}\n{titulo}\n{'─' * 68}")


def correr(fecha: date | None, verboso: bool) -> None:
    grafo = construir()
    estado = estado_inicial(fecha)

    print(f"Agente de monitoreo · {estado['fecha']}")
    print(memoria.resumen_para_prompt(3))

    herramientas_usadas: list[str] = []
    final = None
    for paso in grafo.stream(estado, stream_mode="values"):
        final = paso
        if not paso.get("mensajes"):
            continue
        ultimo = paso["mensajes"][-1]
        for llamada in getattr(ultimo, "tool_calls", []) or []:
            herramientas_usadas.append(llamada["name"])
            print(f"  → {llamada['name']}({', '.join(f'{k}={v}' for k, v in llamada['args'].items())})")

    if final is None:
        print("El grafo no produjo estado.")
        return

    hipotesis = final.get("hipotesis", {})
    critica = final.get("critica", {})
    recomendaciones = final.get("recomendaciones", [])
    corregido = critica.get("veredicto") == "insuficiente"

    _linea("DIAGNÓSTICO (reescrito tras la reflexión)" if corregido else "DIAGNÓSTICO")
    print(f"  {hipotesis.get('titulo', '(sin título)')}")
    print(f"  tipo: {hipotesis.get('tipo')} · alcance: {hipotesis.get('alcance')} "
          f"· severidad: {hipotesis.get('severidad')}")
    print(f"\n  {hipotesis.get('explicacion', '')}")
    if hipotesis.get("evidencia"):
        print("\n  Evidencia:")
        for e in hipotesis["evidencia"]:
            print(f"    · {e}")
    if hipotesis.get("impacto_negocio"):
        print(f"\n  Impacto: {hipotesis['impacto_negocio']}")

    _linea("REFLEXIÓN")
    print(f"  veredicto: {critica.get('veredicto')} · vueltas: {final.get('vueltas', 0)}")
    for o in critica.get("objeciones", []):
        print(f"    · {o}")
    if corregido:
        print("\n  El diagnóstico de arriba ya incorpora estas objeciones.")

    _linea("RECOMENDACIONES")
    for r in recomendaciones:
        print(f"  [{r.get('urgencia', '?')}] {r.get('accion')} → {r.get('objetivo')}")
        print(f"      {r.get('justificacion', '')}")

    acciones = final.get("acciones", [])
    if acciones:
        _linea("ACCIÓN")
        for a in acciones:
            if a.get("ejecutada"):
                print(f"  ✓ {a['accion']} → {a['objetivo']}")
                print(f"      {a.get('modelos_reentrenados')} modelos "
                      f"en {a.get('duracion_s')}s")
                continue
            print(f"  ✗ no se ejecutó: {a.get('motivo', 'sin motivo')}")
            for d in a.get("habria_ejecutado", []):
                print(f"      habría reentrenado: {d.get('filtro') or 'la flota'}")

    if hipotesis.get("tipo") != "sin_hallazgos":
        memoria.registrar(
            fecha=final["fecha"],
            titulo=hipotesis.get("titulo", ""),
            severidad=hipotesis.get("severidad", "baja"),
            alcance=hipotesis.get("alcance", "flota"),
            evidencia=hipotesis.get("evidencia", []),
            recomendaciones=recomendaciones,
        )
        print("\n  (diagnóstico guardado en memoria)")

    if verboso:
        _linea("HERRAMIENTAS LLAMADAS")
        print("  " + ", ".join(herramientas_usadas))


def main() -> None:
    p = argparse.ArgumentParser(prog="agente", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Una corrida del agente")
    r.add_argument("--fecha", type=date.fromisoformat, default=None)
    r.add_argument("--verboso", action="store_true")

    m = sub.add_parser("memoria", help="Qué recuerda el agente")
    m.add_argument("--limpiar", action="store_true")

    args = p.parse_args()

    if args.cmd == "run":
        correr(args.fecha, args.verboso)
    elif args.cmd == "memoria":
        if args.limpiar:
            print(f"Memoria borrada ({memoria.limpiar()} diagnósticos).")
        else:
            print(json.dumps(memoria.historial(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
