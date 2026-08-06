"""La cadena de retail sobre la que corre todo el taller.

24 tiendas x 8 categorias = 192 modelos de pronostico en produccion. Ese numero
es el punto entero del caso: nadie puede vigilar 192 modelos a mano.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ_DATOS = Path(os.getenv("RUTA_DATOS", "/datos"))
RUTA_VENTAS = RAIZ_DATOS / "ventas.csv"
RUTA_PREDICCIONES = RAIZ_DATOS / "predicciones.csv"
RUTA_METRICAS = RAIZ_DATOS / "metricas.csv"
RUTA_MODELOS = RAIZ_DATOS / "modelos"
RUTA_MLRUNS = RAIZ_DATOS / "mlruns"
RUTA_ESTADO = RAIZ_DATOS / "estado.json"
RUTA_LOG_REENTRENAMIENTOS = RAIZ_DATOS / "reentrenamientos.json"

# (nombre, region, factor de tamano de la tienda)
TIENDAS: list[tuple[str, str, float]] = [
    ("miraflores", "LIMA", 1.35),
    ("san-isidro", "LIMA", 1.30),
    ("surco", "LIMA", 1.25),
    ("la-molina", "LIMA", 1.15),
    ("san-borja", "LIMA", 1.10),
    ("jesus-maria", "LIMA", 1.00),
    ("magdalena", "LIMA", 0.95),
    ("san-miguel", "LIMA", 1.05),
    ("los-olivos", "LIMA", 1.20),
    ("comas", "LIMA", 1.00),
    ("ate", "LIMA", 0.95),
    ("chorrillos", "LIMA", 0.90),
    ("villa-el-salvador", "LIMA", 0.85),
    ("callao", "LIMA", 1.05),
    ("trujillo", "NORTE", 1.10),
    ("chiclayo", "NORTE", 1.00),
    ("piura", "NORTE", 0.95),
    ("chimbote", "NORTE", 0.80),
    ("arequipa", "SUR", 1.15),
    ("tacna", "SUR", 0.85),
    ("juliaca", "SUR", 0.75),
    ("cusco", "SUR", 0.90),
    ("huancayo", "CENTRO", 0.90),
    ("iquitos", "ORIENTE", 0.80),
]

# (nombre, demanda base diaria, amplitud de estacionalidad semanal)
CATEGORIAS: list[tuple[str, float, float]] = [
    ("lacteos", 320, 0.18),
    ("bebidas", 410, 0.34),
    ("abarrotes", 500, 0.12),
    ("panaderia", 280, 0.22),
    ("carnes", 190, 0.30),
    ("limpieza", 150, 0.10),
    ("cuidado-personal", 130, 0.14),
    ("congelados", 160, 0.26),
]

NOMBRES_TIENDAS = [t for t, _, _ in TIENDAS]
NOMBRES_CATEGORIAS = [c for c, _, _ in CATEGORIAS]
REGION_DE = {t: r for t, r, _ in TIENDAS}


def modelo_id(categoria: str, tienda: str) -> str:
    """Identificador del modelo. Un artefacto por categoria y tienda."""
    return f"dem-{categoria}-{tienda}"


def todos_los_modelos() -> list[dict[str, str]]:
    return [
        {
            "modelo_id": modelo_id(c, t),
            "categoria": c,
            "tienda": t,
            "region": REGION_DE[t],
        }
        for c in NOMBRES_CATEGORIAS
        for t in NOMBRES_TIENDAS
    ]


HORIZONTE_DIAS = 14
