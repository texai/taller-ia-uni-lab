"""Que hay dentro del volumen de datos, y como asomarse a un archivo.

Existe por la primera pregunta que hace todo el mundo despues del primer
comando del taller:

    $ make seed
    ... Listo. 192 modelos con 17,472 dias-modelo de telemetria.
    $ ls
    Makefile  README.md  agente  docker-compose.yml  guias  plataforma  retos  ui

No hay ninguna carpeta nueva, y parece que el comando no hizo nada.

Si la hizo. Lo que pasa es que /datos no esta en el disco de nadie: es un
**volumen** de Docker (`volumes: datos:` al final de docker-compose.yml), que
es almacenamiento que gestiona Docker y que solo se ve desde dentro de un
contenedor. Un montaje de carpeta —`./plataforma:/app/plataforma`, dos lineas
mas arriba— si se veria; un volumen con nombre, no.

Y es deliberado: 7 MB de CSV y 192 artefactos binarios regenerables no tienen
por que aterrizar en el repositorio de nadie ni acabar en un `git status`.
El precio es este modulo, que es la unica forma de mirar adentro.
"""

from __future__ import annotations

from pathlib import Path

from plataforma.config import (
    RAIZ_DATOS,
    RUTA_METRICAS,
    RUTA_MODELOS,
    RUTA_PREDICCIONES,
    RUTA_VENTAS,
)

# Que es cada cosa, en una linea. El orden es el del pipeline, no el
# alfabetico: es el orden en el que `make seed` los va creando.
QUE_ES: dict[str, str] = {
    "ventas.csv": "el mundo, dos anos de historia",
    "modelos/": "un .joblib por modelo, mas registro.json",
    "predicciones.csv": "lo que escribio el job",
    "metricas.csv": "lo unico que el agente mira",
    "ejecuciones_job.csv": "la bitacora del job",
    "estado.json": "en que dia se quedo la plataforma",
    "reentrenamientos.json": "lo que el agente pidio reentrenar",
    "mlruns/": "el registro de MLflow, si se levanto",
}

ORDEN = list(QUE_ES)


def _tamano(n: int) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _filas(ruta: Path) -> int | None:
    """Filas de datos de un CSV, sin contar la cabecera.

    Se cuenta a mano en vez de con pandas porque `ventas.csv` son 4 MB y esto
    se ejecuta delante de la clase: leerlo entero a un DataFrame para saber
    cuantas filas tiene tarda lo suficiente como para que alguien pregunte si
    se colgo.
    """
    if ruta.suffix != ".csv":
        return None
    with ruta.open("r", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def inventario() -> list[dict[str, object]]:
    """Lo que hay hoy en el volumen, una entrada por archivo o carpeta."""
    if not RAIZ_DATOS.exists():
        return []

    encontrados: dict[str, Path] = {}
    for hijo in RAIZ_DATOS.iterdir():
        encontrados[hijo.name + "/" if hijo.is_dir() else hijo.name] = hijo

    # Primero los conocidos y en orden de pipeline; despues cualquier cosa que
    # aparezca y no este en la tabla, para que un archivo nuevo no se vuelva
    # invisible solo porque nadie actualizo este modulo.
    nombres = [n for n in ORDEN if n in encontrados]
    nombres += sorted(n for n in encontrados if n not in QUE_ES)

    filas: list[dict[str, object]] = []
    for nombre in nombres:
        ruta = encontrados[nombre]
        if ruta.is_dir():
            hijos = list(ruta.rglob("*"))
            filas.append(
                {
                    "nombre": nombre,
                    "cuantos": sum(1 for h in hijos if h.is_file()),
                    "unidad": "archivos",
                    "bytes": sum(h.stat().st_size for h in hijos if h.is_file()),
                    "que_es": QUE_ES.get(nombre, ""),
                }
            )
        else:
            n = _filas(ruta)
            filas.append(
                {
                    "nombre": nombre,
                    "cuantos": n,
                    "unidad": "filas" if n is not None else "",
                    "bytes": ruta.stat().st_size,
                    "que_es": QUE_ES.get(nombre, ""),
                }
            )
    return filas


def imprimir_inventario() -> None:
    filas = inventario()
    if not filas:
        print(f"{RAIZ_DATOS} esta vacio. Corre:  make seed")
        return

    print(f"{RAIZ_DATOS}  ·  volumen `datos` de Docker, no una carpeta del repo\n")
    for f in filas:
        cuantos = f["cuantos"]
        # `ejecuciones_job.csv` tiene UNA fila recien sembrado, y es la primera
        # que se mira en clase: «1 filas» ahi se lee como un error del programa.
        unidad = str(f["unidad"])
        if cuantos == 1 and unidad:
            unidad = unidad.removesuffix("s")
        cuenta = f"{cuantos:,} {unidad}" if cuantos is not None else ""
        print(
            f"  {f['nombre']:<24}{cuenta:>18}"
            f"{_tamano(int(f['bytes'])):>12}   {f['que_es']}"
        )
    print("\nPara asomarte a uno:  make archivos ARGS=\"--ver metricas.csv\"")


# Los cuatro que se miran en clase. La clave es lo que se teclea; se acepta
# tambien el nombre completo del archivo.
ATAJOS: dict[str, Path] = {
    "ventas": RUTA_VENTAS,
    "predicciones": RUTA_PREDICCIONES,
    "metricas": RUTA_METRICAS,
    "modelos": RUTA_MODELOS,
}


def resolver(nombre: str) -> Path:
    clave = nombre.removesuffix(".csv")
    if clave in ATAJOS:
        return ATAJOS[clave]
    return RAIZ_DATOS / nombre


def asomarse(nombre: str, filas: int = 5) -> None:
    """Las primeras lineas de un archivo, sin salir del contenedor."""
    ruta = resolver(nombre)

    if not ruta.exists():
        print(f"No existe {ruta}.")
        print("Lo que si hay:")
        for f in inventario():
            print(f"  {f['nombre']}")
        return

    if ruta.is_dir():
        hijos = sorted(h.name for h in ruta.iterdir())
        print(f"{ruta}  ·  {len(hijos)} archivos. Los primeros {filas}:\n")
        for h in hijos[:filas]:
            print(f"  {h}")
        return

    print(f"{ruta}\n")
    with ruta.open("r", encoding="utf-8") as f:
        for i, linea in enumerate(f):
            if i > filas:
                break
            print(f"  {linea.rstrip()}")
