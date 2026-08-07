"""Convierte cada guia de `guias/*.md` en un PDF con el membrete de la UNI.

    python3 guias/generar.py

Markdown -> HTML con CSS de impresion -> PDF por Chromium. Sin LaTeX y sin
cadenas de herramientas: lo unico que hace falta es Playwright, que ya se usa
para otras cosas del taller.

El membrete sale de la plantilla oficial del programa: el sello de la UNI, el
granate 8F0C0C y las dos lineas de la facultad. El resto del diseno NO se
copia de la plantilla -- esa es de diapositivas y esto son documentos que se
leen en pantalla o impresos, que no es lo mismo.

El logo va incrustado en el HTML como data URI para que el archivo intermedio
se pueda abrir suelto sin que se rompa la imagen.
"""

from __future__ import annotations

import asyncio
import base64
import os
import pathlib
import sys

import markdown

AQUI = pathlib.Path(__file__).parent
LOGO = AQUI / "recursos" / "uni.png"

GRANATE = "#8F0C0C"
FACULTAD = "Facultad de Ingeniería Económica, Estadística y Ciencias Sociales"
CENTRO = "Centro de Formación Continua"
PROGRAMA = (
    "MÓDULO III · Herramientas para la Inteligencia Artificial Generativa "
    "y aplicaciones para la industria"
)
TALLER = "Taller 02 de caso aplicado de IA en industria"

CSS = f"""
@page {{
  size: A4;
  margin: 22mm 16mm 18mm 16mm;
}}

html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}

body {{
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: #1a1d21;
  margin: 0;
}}

/* --------------------------------------------------------------- membrete */

.membrete {{
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 3px solid {GRANATE};
  padding-bottom: 10px;
  margin-bottom: 22px;
}}
.membrete img {{ height: 52px; width: auto; }}
.membrete .facultad {{
  font-size: 8.5pt;
  line-height: 1.35;
  color: {GRANATE};
  font-weight: 600;
  letter-spacing: .01em;
}}
.membrete .centro {{ font-weight: 400; color: #6b7280; }}

.programa {{
  font-size: 8pt;
  color: #6b7280;
  margin: -14px 0 26px;
  line-height: 1.4;
}}

/* ------------------------------------------------------------------ texto */

h1 {{
  font-size: 22pt;
  letter-spacing: -0.02em;
  margin: 0 0 .15em;
  color: {GRANATE};
}}
h1 + p {{ color: #56616e; font-size: 11pt; margin: 0 0 .2em; }}

h2 {{
  font-size: 14pt;
  letter-spacing: -0.01em;
  margin: 1.7em 0 .5em;
  padding-bottom: .25em;
  border-bottom: 2px solid #e9d3d3;
  color: {GRANATE};
  page-break-after: avoid;
}}
h3 {{
  font-size: 11.5pt;
  margin: 1.4em 0 .35em;
  color: #1a1d21;
  page-break-after: avoid;
}}

p, li {{ margin: .5em 0; }}
ul, ol {{ padding-left: 1.3em; }}
strong {{ color: #0f1115; }}

code {{
  font-family: "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
  font-size: .88em;
  background: #f4f1f1;
  padding: .1em .3em;
  border-radius: 3px;
}}
pre {{
  background: #faf7f7;
  border: 1px solid #e9d3d3;
  border-left: 3px solid {GRANATE};
  border-radius: 4px;
  padding: 10px 12px;
  overflow-x: auto;
  page-break-inside: avoid;
}}
pre code {{ background: none; padding: 0; font-size: 9pt; line-height: 1.45; }}

blockquote {{
  margin: 1.1em 0;
  padding: .1em 0 .1em 14px;
  border-left: 3px solid #d9b8b8;
  color: #4b5563;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  margin: 1.1em 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}}
th, td {{
  border-bottom: 1px solid #e9d3d3;
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}}
th {{ color: {GRANATE}; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .04em; }}

hr {{ border: 0; border-top: 1px solid #e9d3d3; margin: 1.8em 0; }}

/* Una tabla o un bloque partido a la mitad por un salto de pagina es lo que
   hace que una guia impresa se lea peor que la misma en pantalla. */
h2, h3, pre, table, blockquote {{ break-inside: avoid; }}
"""


def envolver(titulo: str, cuerpo: str, logo_uri: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>{titulo}</title>
<style>{CSS}</style>
</head><body>
  <div class="membrete">
    <img src="{logo_uri}" alt="Universidad Nacional de Ingeniería">
    <div class="facultad">
      {FACULTAD}<br>
      <span class="centro">{CENTRO} · Universidad Nacional de Ingeniería</span>
    </div>
  </div>
{cuerpo}
  <p class="programa" style="margin-top:26px;border-top:1px solid #e9d3d3;padding-top:8px">
    {PROGRAMA}<br>{TALLER}
  </p>
</body></html>"""


async def a_pdf(trabajos: list[tuple[pathlib.Path, pathlib.Path]]) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Un Chromium ya instalado, si `PLAYWRIGHT_CHROMIUM` lo señala. La
        # version que Playwright espera y la que hay en la maquina no siempre
        # coinciden, y para imprimir un PDF da igual cual sea.
        ruta = os.getenv("PLAYWRIGHT_CHROMIUM")
        navegador = await p.chromium.launch(
            executable_path=ruta if ruta and pathlib.Path(ruta).exists() else None
        )
        pagina = await navegador.new_page()
        for html, destino in trabajos:
            await pagina.goto(html.as_uri(), wait_until="load")
            await pagina.pdf(
                path=str(destino),
                format="A4",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                display_header_footer=True,
                header_template="<div></div>",
                # El pie lleva el numero de pagina y nada mas: el membrete ya
                # dice de quien es el documento, y repetirlo en cada pagina
                # gasta espacio que la guia necesita.
                footer_template=(
                    '<div style="width:100%;font-size:7.5pt;color:#9aa0a6;'
                    'text-align:center;padding:0 16mm 8mm">'
                    '<span class="pageNumber"></span> / '
                    '<span class="totalPages"></span></div>'
                ),
            )
            print(f"  {destino.name}")
        await navegador.close()


def main() -> None:
    if not LOGO.exists():
        sys.exit(f"Falta el sello de la UNI en {LOGO}")
    logo_uri = "data:image/png;base64," + base64.b64encode(
        LOGO.read_bytes()
    ).decode("ascii")

    # El README es el indice, no una guia: sale en GitHub y no hace falta
    # imprimirlo.
    fuentes = [g for g in sorted(AQUI.glob("*.md")) if g.name != "README.md"]
    if not fuentes:
        sys.exit("No hay ninguna guia en guias/*.md")

    # El HTML va oculto —es un paso intermedio— pero el PDF no: si el PDF
    # heredara el punto del intermedio, el entregable saldria invisible.
    trabajos: list[tuple[pathlib.Path, pathlib.Path]] = []
    for md in fuentes:
        texto = md.read_text(encoding="utf-8")
        titulo = next(
            (l[2:].strip() for l in texto.split("\n") if l.startswith("# ")), md.stem
        )
        cuerpo = markdown.markdown(
            texto,
            extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        )
        html = AQUI / f".{md.stem}.html"
        html.write_text(envolver(titulo, cuerpo, logo_uri), encoding="utf-8")
        trabajos.append((html, AQUI / f"{md.stem}.pdf"))

    print(f"{len(fuentes)} guías:")
    asyncio.run(a_pdf(trabajos))

    # Dejar los HTML sueltos invita a editarlos, y lo que se edita es el
    # markdown.
    for html, _ in trabajos:
        html.unlink()


if __name__ == "__main__":
    main()
