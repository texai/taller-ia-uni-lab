"""Linea de comandos de la plataforma.

    python -m plataforma datos       --dias 400
    python -m plataforma entrenar    --hasta 2026-06-30
    python -m plataforma pronosticar --desde 2026-07-01 --hasta 2026-08-05
    python -m plataforma metricas
    python -m plataforma escenario   --nombre sesgo_silencioso
    python -m plataforma seed        # encadena los cuatro primeros
    python -m plataforma archivos    --ver metricas.csv

En clase se usan los atajos del Makefile, pero conviene que los alumnos vean
que detras no hay magia.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from plataforma import archivos, datos, entrenar, escenario, metricas, pronosticar
from plataforma.config import RUTA_VENTAS


def _fecha(valor: str) -> date:
    return date.fromisoformat(valor)


def _corte_por_defecto(dias_evaluacion: int = 90) -> date:
    """Ultimo dia de entrenamiento: deja los ultimos meses para evaluar."""
    return date.today() - timedelta(days=dias_evaluacion + 1)


def main() -> None:
    p = argparse.ArgumentParser(prog="plataforma", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("datos", help="Genera el historico de ventas")
    d.add_argument("--dias", type=int, default=400)
    d.add_argument("--semilla", type=int, default=7)

    e = sub.add_parser("entrenar", help="Entrena los 192 modelos")
    e.add_argument("--hasta", type=_fecha, default=None)

    f = sub.add_parser("pronosticar", help="Corre el job batch")
    f.add_argument("--desde", type=_fecha, default=None)
    f.add_argument("--hasta", type=_fecha, default=None)

    m = sub.add_parser("metricas", help="Cruza pronostico contra realidad")
    m.add_argument("--desde", type=_fecha, default=None)
    m.add_argument("--hasta", type=_fecha, default=None)

    s = sub.add_parser("escenario", help="Degrada el mundo")
    s.add_argument("--nombre", required=True, choices=escenario.ESCENARIOS)
    s.add_argument("--desde", type=_fecha, default=None)
    s.add_argument("--categoria", default=None)
    s.add_argument("--tienda", default=None)

    sub.add_parser("seed", help="Pipeline completo desde cero")

    a = sub.add_parser("archivos", help="Que hay dentro del volumen /datos")
    a.add_argument("--ver", default=None, help="Asomarse a uno: metricas.csv")
    a.add_argument("--filas", type=int, default=5)

    args = p.parse_args()
    corte = _corte_por_defecto()

    if args.cmd == "datos":
        n = datos.generar(dias=args.dias, semilla=args.semilla)
        print(f"Historico generado: {n:,} filas en {RUTA_VENTAS}")

    elif args.cmd == "entrenar":
        r = entrenar.entrenar(hasta=args.hasta or corte)
        print(f"Flota entrenada: {r['modelos']} modelos hasta {r['entrenado_hasta']}")

    elif args.cmd == "pronosticar":
        r = pronosticar.pronosticar(
            desde=args.desde or corte + timedelta(days=1),
            hasta=args.hasta or date.today(),
        )
        print(f"Job batch: {r['predicciones']:,} predicciones en {r['duracion_s']}s")

    elif args.cmd == "metricas":
        r = metricas.calcular(desde=args.desde, hasta=args.hasta)
        print(f"Metricas: {r['filas']:,} filas sobre {r['modelos']} modelos")

    elif args.cmd == "escenario":
        r = escenario.aplicar(
            args.nombre, desde=args.desde, categoria=args.categoria, tienda=args.tienda
        )
        print(f"Escenario '{r['escenario']}' aplicado desde {r['desde']}")
        print(f"  filas afectadas: {r['filas_afectadas']:,}")
        print("  ahora corre:  make pronosticar && make metricas")

    elif args.cmd == "archivos":
        if args.ver:
            archivos.asomarse(args.ver, filas=args.filas)
        else:
            archivos.imprimir_inventario()

    elif args.cmd == "seed":
        print("1/4 Generando historico de ventas...")
        datos.generar()
        print("2/4 Entrenando la flota (192 modelos)...")
        entrenar.entrenar(hasta=corte)
        print("3/4 Corriendo el job batch de pronostico...")
        pronosticar.pronosticar(desde=corte + timedelta(days=1), hasta=date.today())
        print("4/4 Calculando metricas...")
        r = metricas.calcular()
        print(f"\nListo. {r['modelos']} modelos con {r['filas']:,} dias-modelo de telemetria.")


if __name__ == "__main__":
    main()
