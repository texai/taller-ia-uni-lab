# El deck

`taller.md` es la fuente. `taller.pdf` es lo que sube al aula virtual.

Está escrito en Markdown con [Marp](https://marp.app), así que se edita como
texto y el control de versiones muestra cambios legibles — no un binario que
solo dice "algo cambió".

## Volver a generarlo

```bash
npx @marp-team/marp-cli taller.md --theme tema.css --pdf -o taller.pdf
npx @marp-team/marp-cli taller.md --theme tema.css --html -o taller.html
```

El HTML sirve para presentar desde el navegador: flechas para avanzar y `p`
para el modo presentador con notas.

## Sobre las cifras

Todos los números del deck salieron de correr el laboratorio, no de una
estimación. Si cambias un umbral o la intensidad de un escenario, vuelve a
medir antes de reimprimir:

```bash
make verificar
```
