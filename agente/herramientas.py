"""Las herramientas de percepcion: los ojos del agente.

Reglas de diseno que conviene explicar en clase, porque no son obvias:

1. **Devuelven agregados, no filas.** La telemetria cruda son mas de 17 000
   filas. Si una herramienta se las entrega al modelo, el prompt se dispara,
   el costo se dispara y el modelo se pierde. Cada herramienta responde con
   decenas de numeros, no con miles.

2. **Son de solo lectura.** El agente interroga la plataforma; no toca los
   artefactos ni los contenedores. En produccion nadie le da permiso de
   escritura a un agente sobre los modelos.

3. **La estadistica la hace Python, no el LLM.** El modelo razona sobre los
   numeros; no los calcula. Pedirle a un LLM que compute un KS es caro y poco
   confiable.
"""

from __future__ import annotations

import os
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from langchain_core.tools import tool
from scipy import stats

URL = os.getenv("URL_PLATAFORMA", "http://plataforma:8000")
TIEMPO_ESPERA = 60.0


def _get(ruta: str, **params) -> Any:
    limpios = {k: v for k, v in params.items() if v is not None}
    r = httpx.get(f"{URL}{ruta}", params=limpios, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    return r.json()


def _metricas(desde: date | None = None, hasta: date | None = None, **filtros):
    return _get(
        "/v1/metricas",
        desde=desde.isoformat() if desde else None,
        hasta=hasta.isoformat() if hasta else None,
        **filtros,
    )


def _ultima_fecha(filas: list[dict]) -> date:
    return max(date.fromisoformat(f["fecha"]) for f in filas)


def _media(valores) -> float:
    vals = [v for v in valores if v is not None]
    return round(statistics.fmean(vals), 3) if vals else 0.0


# --------------------------------------------------------------------------
# Inventario
# --------------------------------------------------------------------------


@tool
def listar_modelos() -> dict:
    """Inventario de la flota: cuantos modelos hay en produccion, de que
    version, y como se reparten por categoria y region. Usalo primero, para
    saber sobre que estas trabajando."""
    modelos = _get("/v1/modelos")
    por_categoria: dict[str, int] = defaultdict(int)
    por_region: dict[str, int] = defaultdict(int)
    for m in modelos:
        por_categoria[m["categoria"]] += 1
        por_region[m["region"]] += 1
    return {
        "total_modelos": len(modelos),
        "por_categoria": dict(por_categoria),
        "por_region": dict(por_region),
        "entrenados_hasta": modelos[0]["entrenado_hasta"] if modelos else None,
        "mape_validacion_medio": _media(m["mape_validacion"] for m in modelos),
    }


# --------------------------------------------------------------------------
# Percepcion: estado general
# --------------------------------------------------------------------------


@tool
def resumen_flota(dias: int = 14) -> dict:
    """Salud de los 192 modelos en los ultimos `dias`: error medio, sesgo,
    cobertura del intervalo, y los peores modelos por cada senal.

    Es el punto de partida de cualquier diagnostico. Fijate en las dos
    senales por separado: un MAPE alto y un sesgo alto NO significan lo
    mismo. El sesgo dice hacia que lado se equivoca el modelo, y un sesgo
    sostenido cuesta plata aunque el MAPE se vea normal."""
    filas = _metricas()
    if not filas:
        return {"error": "Sin telemetria. Corre: make seed"}

    corte = _ultima_fecha(filas) - timedelta(days=dias - 1)
    v = [f for f in filas if date.fromisoformat(f["fecha"]) >= corte]

    por_modelo: dict[str, list[dict]] = defaultdict(list)
    for f in v:
        por_modelo[f["modelo_id"]].append(f)

    resumen = []
    for mid, fs in por_modelo.items():
        resumen.append(
            {
                "modelo_id": mid,
                "categoria": fs[0]["categoria"],
                "tienda": fs[0]["tienda"],
                "region": fs[0]["region"],
                "mape": _media(f["mape"] for f in fs),
                "sesgo_pct": _media(f["sesgo_pct"] for f in fs),
                "cobertura": _media(f["cobertura"] for f in fs),
                "dias_en_promocion": sum(f["dias_en_promocion"] for f in fs),
                "dias_con_quiebre": sum(f["dias_con_quiebre"] for f in fs),
            }
        )

    return {
        "ventana_dias": dias,
        "desde": corte.isoformat(),
        "hasta": _ultima_fecha(filas).isoformat(),
        "modelos_evaluados": len(resumen),
        "global": {
            "mape_medio": _media(r["mape"] for r in resumen),
            "sesgo_medio_pct": _media(r["sesgo_pct"] for r in resumen),
            "cobertura_media": _media(r["cobertura"] for r in resumen),
            "modelos_con_mape_sobre_25": sum(r["mape"] > 25 for r in resumen),
            "modelos_con_sesgo_sobre_10": sum(abs(r["sesgo_pct"]) > 10 for r in resumen),
        },
        "peores_por_mape": sorted(resumen, key=lambda r: -r["mape"])[:8],
        "peores_por_sesgo": sorted(resumen, key=lambda r: -abs(r["sesgo_pct"]))[:8],
    }


@tool
def agregado_por(dimension: str = "categoria", dias: int = 14) -> dict:
    """Promedia las metricas por `categoria`, `tienda` o `region`.

    Es la herramienta que revela la FORMA de un problema. Si la degradacion
    se concentra en una categoria y aparece en todas las tiendas, la causa
    es del producto. Si se concentra en una tienda y toca a todas las
    categorias, la causa es de esa tienda. Un modelo suelto degradado es
    otra cosa."""
    if dimension not in ("categoria", "tienda", "region"):
        return {"error": "dimension debe ser: categoria, tienda o region"}

    filas = _metricas()
    if not filas:
        return {"error": "Sin telemetria. Corre: make seed"}
    corte = _ultima_fecha(filas) - timedelta(days=dias - 1)
    v = [f for f in filas if date.fromisoformat(f["fecha"]) >= corte]

    grupos: dict[str, list[dict]] = defaultdict(list)
    for f in v:
        grupos[f[dimension]].append(f)

    salida = [
        {
            dimension: clave,
            "n_modelos": len({f["modelo_id"] for f in fs}),
            "mape": _media(f["mape"] for f in fs),
            "sesgo_pct": _media(f["sesgo_pct"] for f in fs),
            "cobertura": _media(f["cobertura"] for f in fs),
            "unidades_reales": round(sum(f["unidades_reales"] for f in fs)),
        }
        for clave, fs in grupos.items()
    ]
    return {
        "dimension": dimension,
        "ventana_dias": dias,
        "grupos": sorted(salida, key=lambda g: -g["mape"]),
    }


# --------------------------------------------------------------------------
# Percepcion: deriva
# --------------------------------------------------------------------------


@tool
def comparar_periodos(
    dias_recientes: int = 14, dias_base: int = 45, dimension: str = "categoria"
) -> dict:
    """Compara una ventana reciente contra una linea base anterior y mide si
    la diferencia es estadisticamente real.

    Devuelve, por grupo: el error antes y despues, el sesgo antes y despues,
    y un test de Kolmogorov-Smirnov sobre la distribucion diaria del error.
    Un p-valor bajo dice que la distribucion cambio de verdad, no que tuviste
    una mala semana.

    Compara SIEMPRE los dos deltas. Que el MAPE se mueva poco mientras el
    sesgo se dispara es una senal distinta a que suban ambos, y suele ser la
    mas cara."""
    if dimension not in ("categoria", "tienda", "region"):
        return {"error": "dimension debe ser: categoria, tienda o region"}

    filas = _metricas()
    if not filas:
        return {"error": "Sin telemetria. Corre: make seed"}

    fin = _ultima_fecha(filas)
    corte = fin - timedelta(days=dias_recientes - 1)
    inicio_base = corte - timedelta(days=dias_base)

    base: dict[str, list[dict]] = defaultdict(list)
    reciente: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        d = date.fromisoformat(f["fecha"])
        if inicio_base <= d < corte:
            base[f[dimension]].append(f)
        elif d >= corte:
            reciente[f[dimension]].append(f)

    salida = []
    for clave in sorted(set(base) | set(reciente)):
        b, r = base.get(clave, []), reciente.get(clave, [])
        if len(b) < 10 or len(r) < 10:
            continue
        mape_b, mape_r = _media(f["mape"] for f in b), _media(f["mape"] for f in r)
        ks, p = stats.ks_2samp([f["mape"] for f in b], [f["mape"] for f in r])
        salida.append(
            {
                dimension: clave,
                "mape_base": mape_b,
                "mape_reciente": mape_r,
                "delta_mape_pct": round((mape_r - mape_b) / max(mape_b, 0.01) * 100, 1),
                "sesgo_base": _media(f["sesgo_pct"] for f in b),
                "sesgo_reciente": _media(f["sesgo_pct"] for f in r),
                "delta_sesgo_pp": round(
                    _media(f["sesgo_pct"] for f in r) - _media(f["sesgo_pct"] for f in b), 2
                ),
                "ks": round(float(ks), 4),
                "p_valor": round(float(p), 6),
                "cambio_significativo": bool(p < 0.01),
            }
        )

    return {
        "dimension": dimension,
        "base": {"desde": inicio_base.isoformat(), "hasta": (corte - timedelta(days=1)).isoformat()},
        "reciente": {"desde": corte.isoformat(), "hasta": fin.isoformat()},
        "grupos": sorted(salida, key=lambda g: -abs(g["delta_mape_pct"])),
    }


# --------------------------------------------------------------------------
# Percepcion: anomalias
# --------------------------------------------------------------------------


@tool
def detectar_anomalias(dias: int = 21) -> dict:
    """Busca discontinuidades: caidas subitas de volumen, dias sin ventas,
    saltos de latencia.

    Una anomalia NO es deriva. La deriva es el mundo cambiando de a poco y
    el modelo quedandose atras; una anomalia es algo que se rompio. Si una
    tienda deja de reportar, el modelo esta sano y el problema es del feed
    de datos. Recomendar un reentrenamiento ahi seria un error caro."""
    filas = _metricas()
    if not filas:
        return {"error": "Sin telemetria. Corre: make seed"}

    fin = _ultima_fecha(filas)
    corte = fin - timedelta(days=dias - 1)

    por_tienda: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in filas:
        if date.fromisoformat(f["fecha"]) >= corte:
            por_tienda[f["tienda"]][f["fecha"]] += f["unidades_reales"]

    hallazgos = []
    for tienda, por_dia in por_tienda.items():
        serie = [por_dia[k] for k in sorted(por_dia)]
        if len(serie) < 7:
            continue
        mediana = statistics.median(serie)
        if mediana <= 0:
            continue
        dias_caidos = [
            fecha
            for fecha in sorted(por_dia)
            if por_dia[fecha] < mediana * 0.2
        ]
        if dias_caidos:
            hallazgos.append(
                {
                    "tipo": "caida_de_volumen",
                    "tienda": tienda,
                    "dias_afectados": len(dias_caidos),
                    "desde": dias_caidos[0],
                    "hasta": dias_caidos[-1],
                    "volumen_mediano": round(mediana),
                    "volumen_en_caida": round(
                        statistics.fmean(por_dia[d] for d in dias_caidos)
                    ),
                    "nota": "Volumen casi nulo sostenido. Revisar el feed de ventas antes de culpar al modelo.",
                }
            )

    latencias = [f["latencia_p95_ms"] for f in filas if date.fromisoformat(f["fecha"]) >= corte]
    base_lat = [f["latencia_p95_ms"] for f in filas if date.fromisoformat(f["fecha"]) < corte]
    if latencias and base_lat and _media(latencias) > _media(base_lat) * 2:
        hallazgos.append(
            {
                "tipo": "degradacion_de_latencia",
                "latencia_p95_base_ms": _media(base_lat),
                "latencia_p95_reciente_ms": _media(latencias),
            }
        )

    return {"ventana_dias": dias, "anomalias": hallazgos, "n_anomalias": len(hallazgos)}


@tool
def estado_del_job() -> dict:
    """Historial del job batch de pronostico: si corrio, cuanto tardo, si
    fallo. Un modelo puede estar perfectamente sano y el job caido."""
    corridas = _get("/v1/job/corridas")
    return {"corridas": corridas[-10:], "total_registradas": len(corridas)}


@tool
def detalle_modelo(modelo_id: str, dias: int = 30) -> dict:
    """Metricas diarias de un modelo puntual. Usalo cuando ya sabes cual
    quieres mirar de cerca; no lo uses para explorar la flota."""
    filas = _metricas(modelo_id=modelo_id)
    if not filas:
        return {"error": f"Sin metricas para {modelo_id}"}
    return {"modelo_id": modelo_id, "dias": filas[-dias:]}


HERRAMIENTAS = [
    listar_modelos,
    resumen_flota,
    agregado_por,
    comparar_periodos,
    detectar_anomalias,
    estado_del_job,
    detalle_modelo,
]
