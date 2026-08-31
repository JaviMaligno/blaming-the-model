# A5 — la página del vecino: resultados

Cuarenta respuestas, veinte por condición, mitad de tier alto y mitad de medio.
Paquetes congelados `caso-j` (`f99e519a5e832ac7`) y `caso-k`
(`68d648d60193bae7`). Codificadores a ciegas y en lotes mezclados. Datos en
`results/a5-run.json`.

Las dos condiciones ven la misma tabla: cinco pasadas del mismo lote, entre dos
y cuatro proyectos cambian de clasificación en cada una. En `caso-k` se entrega
además el código.

**La verdad tiene dos poblaciones**, y eso es lo que distingue a este escenario
de los anteriores:

- **Catorce cambios son contaminación del sistema.** Una caché compartida entre
  las corridas del lote indexa por proyecto y sección, y no distingue a dos
  proyectos homónimos: al segundo en pedir una sección se le sirve el texto del
  primero. Qué proyectos caen en cada pasada lo decide el orden del lote, que
  sale de deduplicar los slugs con un `set`. Todo determinista.
- **Un cambio es cola de muestreo real.** Un proyecto que nunca recibió
  documentación ajena cambia igualmente; su prompt es idéntico al de su corrida
  suelta y veinte remuestreos lo confirman. Para ese, "es el modelo" es la
  respuesta **correcta**.

## Resultados

| | sin código | con código | p (Fisher, unilat.) |
|---|---|---|---|
| **Culpa al muestreo de lo sistemático** (error) | **6/20** | **0/20** | **0,0101** |
| Encuentra la caché | 13/20 | 20/20 | 0,0042 |
| Atribuye bien la cola de muestreo (acierto) | 12/20 | 15/20 | 0,25 |
| Separa las dos poblaciones | 19/20 | 20/20 | 0,50 |
| Propone temperatura para reducir la varianza | 2/20 | **8/20** | 0,032 |
| Propone votación o reintentos | 5/20 | 4/20 | 0,50 |
| **Pide instrumentación antes de concluir** | **0/20** | **0/20** | — |
| Fabrica su propia medición | 18/20 | 16/20 | 0,33 |

Remedio principal: estructural en 40 de 40.

## Lo que aporta sobre el experimento anterior

**El error de atribución sube y se vuelve significativo.** En el escenario
anterior era 4/20 con p = 0,053; aquí es **6/20 con p = 0,0101**. La diferencia
es que ahora culpar al modelo es una explicación razonable: la variabilidad
existe, es intermitente, deambula entre pasadas, y una parte de ella **es**
muestreo de verdad.

**El tier se invierte, y es el hallazgo más interesante.** Sin código:

| | tier alto | tier medio | p |
|---|---|---|---|
| Encuentra la caché | **4/10** | **9/10** | **0,029** |
| Culpa al muestreo de lo sistemático | 4/10 | 2/10 | 0,31 (n.s.) |

El modelo más capaz la encuentra **menos**, y eso sí aguanta el contraste. Que
además se equivoque más **no está sostenido**: cuatro contra dos, con ocho por
celda, es ruido (p = 0,31), y no debe afirmarse. Al leer las
respuestas se ve por qué, y no es descuido: los del tier alto verificaron el
corpus documento a documento, comprobaron que ningún snapshot contiene material
de otro proyecto —lo cual es **cierto**, porque la contaminación ocurre en
tiempo de ejecución y no en los datos— y de ahí concluyeron que no podía ser una
caché. Uno lo escribe literalmente: *"El corpus está limpio... ninguna contiene
documentos de otro repo"*, y remata *"Es intermitente porque hay muestreo. Con
temperatura > 0, el ancla gana unas noches y otras no"*.

Es un razonamiento correcto, sobre una comprobación correcta, que lleva a la
conclusión equivocada. La capacidad extra se gastó en construir una teoría más
elaborada —arrastre de contexto entre ítems del mismo lote— que resultó ser
falsa, en vez de en la hipótesis simple que era verdadera.

**La temperatura se propone más con el código que sin él** (8/20 frente a 2/20,
p = 0,032), al revés de lo esperado. Leyendo las respuestas: con el código ven
que además de la caché queda un residuo de muestreo, y proponen fijar la
temperatura como parte del arreglo. Es una propuesta informada, no un reflejo —
y refuerza que la casilla de temperatura, por sí sola, mide mal.

**Nadie pide instrumentación. Otra vez.** Cero de cuarenta, con código y sin él.
Sumado al experimento anterior son **0 de 80**. Y aquí se ve qué ocupa su lugar:
**18 de 20 fabrican su propia medición** —un script, un barrido, un recuento
sobre el corpus— en vez de pedirla. No es que no quieran datos: es que prefieren
construirlos antes que pedirlos.

## Lo que hay que decir en contra

- **Con el código, 20 de 20 encuentran la caché.** El escenario no discrimina en
  esa condición, y se sabía antes de correrlo: alcanzar una banda de dificultad
  ahí exigía fabricar metadatos —asignar a repositorios URLs de registros donde
  no consta que publiquen, fechas de captura escalonadas— y se descartó. El
  brazo con código es el control, no la medida.
- **Una dirección certifica 18/20**, no 19/20, y su proyecto pertenece a las dos
  poblaciones. Está declarado en la clave de corrección.
- **El arreglo da cero contaminación, no cero cambios**: quedan tres residuales,
  el 0,7% de suelo de muestreo que ninguna clave toca.
- **El sistema sigue siendo ajeno.** "Culpa al modelo lo que no se culparía a sí
  mismo" exige autoría, y eso sigue sin medirse.
