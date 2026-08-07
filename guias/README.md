# Guías del taller

Seis hojas sueltas, cada una sobre una cosa concreta. **No sustituyen a la
clase**: son para tener al lado mientras se trabaja, y para volver a mirarlas
el lunes.

Cada guía está en dos formatos: el `.md` para leer en GitHub y el `.pdf` para
imprimir o subir al aula virtual.

| # | Guía | Para qué |
|---|---|---|
| 1 | [Docker en siete comandos](01-docker-en-siete-comandos.md) | Lo que hay que saber de Docker para este taller, y ni una línea más |
| 2 | [Leer la telemetría](02-leer-la-telemetria.md) | MAPE, sesgo y cobertura: qué dice cada una y cómo se lee mal |
| 3 | [Romper el mundo](03-romper-el-mundo.md) | Los cuatro escenarios, y cómo seguir rompiendo cosas después |
| 4 | [Las siete herramientas](04-las-siete-herramientas.md) | Los ojos del agente y las reglas de una herramienta de percepción |
| 5 | [Anatomía del agente](05-anatomia-del-agente.md) | Del bucle plano al grafo, y por qué esa diferencia importa |
| 6 | [Si algo falla](06-si-algo-falla.md) | Las trece cosas que se rompieron montando esto |

Aparte está el [trabajo previo](../taller-ia-uni-prework.md), que sí hay que
hacer **antes** del sábado.

---

## Regenerar los PDF

```bash
pip install markdown playwright
python3 guias/generar.py
```

El markdown es la fuente; el PDF se genera. Si hay que corregir algo, se
corrige el `.md` y se vuelve a generar — editar el PDF deja los dos
desincronizados sin que nadie lo note.

El membrete sale de la plantilla oficial del programa: el sello de la UNI, el
granate institucional y las dos líneas de la facultad. El resto del diseño no,
porque esa plantilla es de diapositivas y esto son documentos que se leen.

En una máquina donde Playwright no encuentre su Chromium, se le puede señalar
uno ya instalado:

```bash
PLAYWRIGHT_CHROMIUM=/ruta/a/chrome python3 guias/generar.py
```
