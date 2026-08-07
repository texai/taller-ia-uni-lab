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

# Cuanto tiene que moverse una senal para que valga la pena mirarla.
#
# El umbral depende de por donde cortes, y no por gusto: una categoria agrupa
# 24 modelos y una tienda solo 8, asi que el promedio de una tienda se mueve
# mucho mas por puro azar. Medido sobre la flota sana, donde nada esta roto:
#
#   dimension    max delta MAPE   max |delta sesgo|
#   categoria         +19.6%           1.05 pp
#   region            +15.2%           2.31 pp
#   tienda            +48.4%           3.54 pp
#
# Un umbral unico calibrado con categorias marca tres tiendas sanas como
# derivadas y cuatro como sesgadas. El agente cree lo que le dicen las
# banderas, y con razon: el error no es suyo, es de quien puso el umbral.
UMBRALES = {
    #              MAPE %   sesgo pp
    "categoria": (   25.0,      3.0),
    "region":    (   25.0,      4.0),
    "tienda":    (   60.0,      5.0),
}


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


def _percentil(valores: list[float], p: int) -> float:
    vals = sorted(v for v in valores if v is not None)
    if not vals:
        return 0.0
    i = min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1))))
    return round(vals[i], 3)


def _sesgo(filas) -> float:
    """Sesgo de un conjunto de filas, en porcentaje.

    Se calcula como cociente de totales -- cuantas unidades de mas se
    pronostico sobre cuantas se vendieron -- y NO como promedio de los
    sesgos diarios. La diferencia no es cosmetica: el promedio de cocientes
    esta sesgado hacia arriba, porque un dia de venta baja infla su propio
    porcentaje sin mover casi nada el total. Con esa cuenta, una categoria
    con muchas promociones parece sobre-pronosticada aunque no lo este.

    Asi ademas el numero significa algo en el mundo: +12% son 12% de unidades
    de mas en almacen.
    """
    reales = pronosticadas = 0.0
    for f in filas:
        reales += float(f.get("unidades_reales") or 0.0)
        pronosticadas += float(f.get("unidades_pronosticadas") or 0.0)
    if reales <= 0:
        return 0.0
    return round((pronosticadas - reales) / reales * 100, 3)


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
    sostenido cuesta plata aunque el MAPE se vea normal.

    `cobertura` es la fraccion de dias en que la venta real cayo DENTRO del
    intervalo de prediccion del modelo. Lo esperable ronda 0.9. Baja no
    significa que falten datos ni que el modelo no haya corrido: significa que
    el modelo predice con mas confianza de la que merece. Un modelo puede
    tener cobertura 0.07 y aun asi haber pronosticado los 30 dias.

    Ojo con el nivel al que miras. El sesgo de la flota es lo que le importa
    al negocio, porque los excesos de un modelo compensan los faltantes de
    otro en el mismo almacen. Un modelo suelto tiene un sesgo propio de
    varios puntos incluso cuando todo esta bien: por eso viene la
    distribucion (`sesgo_modelo_mediana`, `sesgo_modelo_p90`). Compara
    contra ella antes de declarar que un modelo esta raro; contar cuantos
    superan un umbral fijo, sin saber cual es la dispersion normal, no
    dice nada."""
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
                "sesgo_pct": _sesgo(fs),
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
            "sesgo_pct": _sesgo(v),
            "cobertura_media": _media(r["cobertura"] for r in resumen),
            "unidades_de_mas": round(
                sum(f["unidades_pronosticadas"] for f in v)
                - sum(f["unidades_reales"] for f in v)
            ),
            "modelos_con_mape_sobre_25": sum(r["mape"] > 25 for r in resumen),
            "sesgo_modelo_mediana": _percentil(
                [abs(r["sesgo_pct"]) for r in resumen], 50
            ),
            "sesgo_modelo_p90": _percentil(
                [abs(r["sesgo_pct"]) for r in resumen], 90
            ),
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
            "sesgo_pct": _sesgo(fs),
            "cobertura": _media(f["cobertura"] for f in fs),
            "unidades_reales": round(sum(f["unidades_reales"] for f in fs)),
            "unidades_de_mas": round(
                sum(f["unidades_pronosticadas"] for f in fs)
                - sum(f["unidades_reales"] for f in fs)
            ),
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
    mas cara.

    Cada senal trae su propia bandera, y no significan lo mismo:

    - `deriva_de_error`: el MAPE empeoro de forma significativa Y apreciable.
      Se piden las dos cosas porque con miles de dias-modelo el test da
      significativo por diferencias que a nadie le importan. Toda la flota
      pierde algo de precision con el correr de las semanas desde su
      entrenamiento; eso es envejecimiento normal, no una alarma.
    - `deriva_de_sesgo`: el modelo empezo a errar hacia un lado. Es la senal
      cara y la mas silenciosa: no hace ruido en el MAPE y su linea base en
      una flota sana es practicamente cero, asi que cuando se mueve, se movio
      de verdad.

    Empieza por `resumen`, no por las filas. Un delta grande sin su bandera
    encendida es ruido que ya fue descartado; si las dos listas vienen
    vacias, no hay deriva y no hace falta buscarle una. Y mira CUANTOS
    grupos aparecen, no solo cuales: si casi todos movieron la misma senal,
    la causa no puede ser de ninguno de ellos en particular."""
    if dimension not in UMBRALES:
        return {"error": f"dimension debe ser: {', '.join(UMBRALES)}"}
    min_mape, min_sesgo = UMBRALES[dimension]

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
                "sesgo_base": _sesgo(b),
                "sesgo_reciente": _sesgo(r),
                "delta_sesgo_pp": round(_sesgo(r) - _sesgo(b), 2),
                "ks": round(float(ks), 4),
                "p_valor": round(float(p), 6),
                "deriva_de_error": bool(
                    p < 0.01
                    and abs((mape_r - mape_b) / max(mape_b, 0.01) * 100) >= min_mape
                ),
                "deriva_de_sesgo": bool(abs(_sesgo(r) - _sesgo(b)) >= min_sesgo),
            }
        )

    todas_b = [f for fs in base.values() for f in fs]
    todas_r = [f for fs in reciente.values() for f in fs]

    return {
        "dimension": dimension,
        "base": {"desde": inicio_base.isoformat(), "hasta": (corte - timedelta(days=1)).isoformat()},
        "reciente": {"desde": corte.isoformat(), "hasta": fin.isoformat()},
        # El recuento va primero y a proposito. Leer ocho filas de deltas
        # invita a quedarse con las dos mas grandes; saber que ocho de ocho
        # grupos movieron el sesgo dice algo que ninguna fila dice sola.
        "resumen": {
            "grupos_evaluados": len(salida),
            "umbrales_usados": {"delta_mape_pct": min_mape, "delta_sesgo_pp": min_sesgo},
            "con_deriva_de_error": [g[dimension] for g in salida if g["deriva_de_error"]],
            "con_deriva_de_sesgo": [g[dimension] for g in salida if g["deriva_de_sesgo"]],
            "sesgo_flota_base_pct": _sesgo(todas_b),
            "sesgo_flota_reciente_pct": _sesgo(todas_r),
            "delta_sesgo_flota_pp": round(_sesgo(todas_r) - _sesgo(todas_b), 2),
        },
        "grupos": sorted(salida, key=lambda g: -abs(g["delta_sesgo_pp"])),
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
    inicio_ref = corte - timedelta(days=45)

    # La referencia se toma de ANTES de la ventana que se inspecciona. Medir
    # lo normal con los mismos dias que se estan auditando es como preguntarle
    # a la caida si es una caida: si la tienda lleva tres semanas muda, su
    # mediana recientes es cero y la averia pasa por ser lo habitual.
    referencia: dict[str, list[float]] = defaultdict(list)
    reciente: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dias_vistos: set[str] = set()
    for f in filas:
        d = date.fromisoformat(f["fecha"])
        if inicio_ref <= d < corte:
            referencia[f["tienda"]].append(f["unidades_reales"])
        elif d >= corte:
            reciente[f["tienda"]][f["fecha"]] += f["unidades_reales"]
            dias_vistos.add(f["fecha"])

    hallazgos = []
    esperados = sorted(dias_vistos)
    for tienda, dias_ref in sorted(referencia.items()):
        if len(dias_ref) < 7:
            continue
        # La referencia es por modelo-dia; la ventana se agrega por dia de
        # tienda, asi que se escala por el numero de modelos de la tienda.
        n_modelos = max(1, len({f["modelo_id"] for f in filas if f["tienda"] == tienda}))
        normal = statistics.median(dias_ref) * n_modelos
        if normal <= 0:
            continue

        por_dia = reciente.get(tienda, {})
        sin_datos = [d for d in esperados if d not in por_dia]
        caidos = [d for d in sorted(por_dia) if por_dia[d] < normal * 0.2]

        if sin_datos:
            hallazgos.append(
                {
                    "tipo": "sin_telemetria",
                    "tienda": tienda,
                    "dias_afectados": len(sin_datos),
                    "desde": sin_datos[0],
                    "hasta": sin_datos[-1],
                    "volumen_normal_diario": round(normal),
                    "nota": (
                        "La tienda dejo de reportar. No llegan datos: el modelo "
                        "no se degrado, se quedo ciego. Reentrenar aqui seria un "
                        "error caro. Revisar el feed."
                    ),
                }
            )
        if caidos:
            hallazgos.append(
                {
                    "tipo": "caida_de_volumen",
                    "tienda": tienda,
                    "dias_afectados": len(caidos),
                    "desde": caidos[0],
                    "hasta": caidos[-1],
                    "volumen_normal_diario": round(normal),
                    "volumen_en_caida": round(
                        statistics.fmean(por_dia[d] for d in caidos)
                    ),
                    "nota": "Volumen casi nulo sostenido. Revisar el feed antes de culpar al modelo.",
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
    ejecuciones = _get("/v1/job/ejecuciones")
    return {"ejecuciones": ejecuciones[-10:], "total_registradas": len(ejecuciones)}


@tool
def detalle_modelo(modelo_id: str, dias: int = 30) -> dict:
    """Metricas diarias de un modelo puntual. Usalo cuando ya sabes cual
    quieres mirar de cerca; no lo uses para explorar la flota.

    El identificador es `dem-<categoria>-<tienda>`, por ejemplo
    `dem-panaderia-callao`. No lo inventes: sale de listar_modelos o de las
    listas de peores en resumen_flota.

    En la vista diaria `cobertura` vale 0 o 1: si la venta de ese dia cayo
    dentro del intervalo de prediccion, o no. Una fila con cobertura 0 NO es
    un dia sin datos -- tiene su pronostico y su venta real, ahi al lado. Para
    saber si faltan datos, mira `detectar_anomalias`."""
    filas = _metricas(modelo_id=modelo_id)
    if filas:
        return {"modelo_id": modelo_id, "dias": filas[-dias:]}

    # Un "no existe" a secas invita a reintentar con otra variante del nombre,
    # y ahi se van cinco llamadas. Mejor decirle exactamente cual quiso pedir.
    todos = sorted({f["modelo_id"] for f in _metricas()})
    partes = {p for p in modelo_id.lower().replace("_", "-").split("-") if p != "dem"}
    cercanos = [m for m in todos if partes and partes <= set(m.split("-"))]
    return {
        "error": f"No existe el modelo {modelo_id!r}.",
        "formato": "dem-<categoria>-<tienda>, por ejemplo dem-panaderia-callao",
        "quiza_buscabas": cercanos[:8] or todos[:5],
    }


HERRAMIENTAS = [
    listar_modelos,
    resumen_flota,
    agregado_por,
    comparar_periodos,
    detectar_anomalias,
    estado_del_job,
    detalle_modelo,
]
