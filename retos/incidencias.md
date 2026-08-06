# Lo que se rompió construyendo esto

Material para el cierre del taller, y para la sección de problemas comunes.

Nada de acá es hipotético. Cada entrada ocurrió de verdad mientras se construía
o se probaba el laboratorio, y varias tienen más valor pedagógico que el tema
que estaban interrumpiendo.

---

## Los nueve errores de diseño del agente

**Ninguno estaba en el modelo de lenguaje.** Esa es la tesis del cierre.

### De cableado del grafo

**1 · El contexto no llegaba a la API.**
La conversación arrancaba con puro `SystemMessage`. Anthropic manda el system
en un parámetro aparte de la petición, así que le llegaba con la lista de
mensajes vacía y la rechazaba. Se arregló abriendo con un `HumanMessage` que
lleva el encargo.

**2 · El estado no se propagaba.**
La apertura no volvía al estado, así que al regresar de llamar una herramienta
el agente había perdido su encargo y razonaba a ciegas sobre una lista de
resultados sueltos.

**3 · `ToolNode` leía la clave equivocada.**
`ToolNode` busca `messages`; nuestro estado la llama `mensajes`. Sin
`messages_key="mensajes"` no ejecutaba **ninguna** herramienta. El síntoma es
mudo: el agente responde, suena razonable, y nunca miró un dato.

### Del simulador

**4 · Un simulador que no podía fallar.**
El proveedor `mock` devolvía un texto fijo y nunca llamaba una herramienta. Se
usaba para probar sin gastar tokens, y no verificaba nada: recorría el grafo
sin ejercitar la parte que importaba.

### De estadística bien calculada y mal planteada

**5 · Promediar porcentajes.**
El sesgo de un grupo no es el promedio de los sesgos de sus partes: es la
diferencia de sus totales. Promediando, panadería marcaba **+9.2%** en un mundo
intacto; como cociente de totales, **+0.7%**.

**6 · Medir lo normal con la ventana que auditas.**
Una tienda muda tres semanas tiene mediana cero en esas tres semanas, así que
la avería pasaba por normalidad. La línea base tiene que ser anterior a lo que
se audita.

**7 · Significancia confundida con relevancia.**
Con mil días-modelo, un test de Kolmogorov-Smirnov marca real cualquier cosa.
Toda la flota pierde precisión al alejarse de su fecha de entrenamiento —hasta
+20% de MAPE en un mundo sano— y eso es envejecimiento, no una alarma.

**8 · Ordenar los hallazgos por la métrica ruidosa.**
El MAPE es la señal ruidosa. Ordenando por su delta, el agente reportaba
primero lo que menos importaba.

### De documentación

**9 · Un campo sin definir.**
`cobertura` no estaba explicado en ninguna parte. El agente lo leyó como "días
con predicción disponible" en vez de "días en que la venta real cayó dentro del
intervalo", y gastó **tres objeciones** peleando con una contradicción que no
existía: *"lacteos-cusco tiene cobertura 0.0 en los 30 días, pero el modelo
sigue generando predicciones. Eso es contradictorio."*

Un nombre ambiguo sin definición le cuesta razonamiento a un agente, igual que
a una persona nueva en el equipo.

---

## El agente encontró varios antes que nosotros

Citas literales de sus reflexiones, sobre su propio diagnóstico:

> *"Inventé impacto de negocio. Dije '9,436 unidades de sobre-stock' pero eso
> es el error acumulado del pronóstico, no sobre-stock. **Estoy dramatizando**."*

> *"Usé p-valor bajo como evidencia de anomalía de datos, pero p-valor bajo
> solo significa cambio estadísticamente significativo."*

> *"¿Por qué Callao y Arequipa son anomalía y Miraflores no? La diferencia es
> solo de magnitud, no de naturaleza."*

La última es la crítica correcta a un umbral mal calibrado, escrita por el
agente que lo estaba sufriendo.

Y la que justificó el nodo `revision`, en el mundo del sesgo silencioso, cuando
el titular decía `sin_hallazgos`:

> *"Tengo banderas de sesgo encendidas en 8/8 categorías y 4/5 regiones. Eso NO
> es ruido normal: es un patrón sistemático. **SÍ hay hallazgo: hay DERIVA**."*

Sabía la respuesta. El grafo no le dejaba decirla.

---

## Las trece incidencias del entorno

### Windows

| | Síntoma | Causa | Arreglo |
|---|---|---|---|
| W1 | `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified` | Docker Desktop cerrado. El mensaje habla de un named pipe, que es el canal cliente-motor | Abrirlo y esperar a que la ballena deje de moverse |
| W2 | `make: command not found` | Windows no trae `make` | `taller.ps1`, equivalente en PowerShell |
| W3 | `arriba` dejaba los contenedores en primer plano | `ValueFromRemainingArguments` deja que PowerShell enlace como parámetro cualquier token con guion: `up -d` se ejecutaba como `up` | Pasar un arreglo explícito |
| W4 | `no se puede cargar el archivo taller.ps1` | Política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| W5 | Errores raros dentro del contenedor | Git en Windows convierte a CRLF al clonar | `.gitattributes` con `* text=auto eol=lf` |
| W6 | Un `git pull` parecía no hacer nada | Los avisos del sistema de archivos no cruzan el montaje Windows-contenedor | `WATCHFILES_FORCE_POLLING=true` |

### Todos los sistemas

| | Síntoma | Causa | Arreglo |
|---|---|---|---|
| T1 | 404 en una ruta que está en el archivo. También: la UI reventando por una columna que llegó como texto | El contenedor sirve el código con el que arrancó, no el que hay en disco | `--reload` en uvicorn |
| T2 | 17,304 filas de telemetría en vez de 17,472 | El verificador dejaba el mundo en `feed_caido` | Regenerar los datos limpios al terminar |
| T3 | Disco lleno a mitad de la construcción | 5.9 GB de imágenes más 3.7 GB de caché | Pedir 12 GB libres y `docker builder prune -f` |
| T4 | El primero que corría el agente se comía 90 s de construcción | `arriba` construía solo dos de las tres imágenes | Construir las tres |
| T5 | Docker Desktop cerrado pasaba la verificación | Se comprobaba el cliente, no el motor: `docker compose version` responde con Docker cerrado | Preguntar por `docker info` |
| T6 | Mensajes de commit corruptos | Comillas invertidas dentro de comillas dobles en bash: se ejecutan como comandos | Pasar el mensaje por archivo |
| T7 | La acción nunca se disparaba | La política frenaba por urgencia, y la urgencia es opinión editorial del agente, no una propiedad de seguridad | Frenar por radio de daño |

**T1 vale por sí solo como material de clase.** Apareció tres veces con tres
síntomas distintos —un plugin que faltaba, una columna que llegaba como texto,
un 404 en una ruta que estaba ahí— y era el mismo error cada vez. Es típico de
cualquier laboratorio con volúmenes montados.

---

## La frase del cierre

**Cuando un agente se equivoca, la primera sospecha no debería ser el modelo.
Casi siempre es lo que le diste de comer.**
