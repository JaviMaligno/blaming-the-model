# Run de confirmación

Fecha: 2026-08-31. Cuarenta respuestas, veinte por condición, diez de tier alto
y diez de tier medio en cada una. Escenarios congelados (`caso-f` digest
`5fc1893dee753499`, `caso-g` digest `33c8686e047c5e73`) sobre el commit
`282489f`. Datos en `results/confirmacion.json`.

Las dos condiciones tienen **exactamente la misma variabilidad**: cinco pasadas
del mismo lote de 24 proyectos, tres de los cuales cambian de código entre
pasadas. Lo único que cambia es que en D se entrega además el código del
sistema.

La causa real es la misma en las dos: el buscador recorre el índice en un orden
derivado del identificador de la petición, así que los empates se resuelven
distinto en cada pasada y llegan documentos distintos al modelo. **La
variabilidad viene de la entrada, no del muestreo.**

Los codificadores trabajaron a ciegas, con las cuarenta respuestas mezcladas y
sin saber de qué condición venía cada una.

## Resultados

| | C: sin código | D: con código | p (Fisher, unilat.) |
|---|---|---|---|
| Encuentra la causa real | 3/20 | **20/20** | < 0,0001 |
| Propone votación o reintentos | 18/20 | 5/20 | < 0,0001 |
| **Propone estabilizar el síntoma** (votación o temperatura) | **19/20** | **9/20** | **0,0006** |
| Plantea que lo que varía es la entrada | 15/20 | 20/20 | 0,024 |
| Muestreo como causa principal | 4/20 | 0/20 | 0,053 |
| Menciona el muestreo en algún grado | 19/20 | 20/20 | 0,50 |
| Propone tocar la temperatura | 10/20 | 6/20 | 0,17 |
| **Pide instrumentación antes de concluir** | **0/20** | **0/20** | — |

Causa principal declarada — C: taxonomía 11, muestreo 4, código del harness 3,
contexto y truncado 2. D: código del harness 20/20.

Remedio principal — C: estructural 13, interruptor 3, instrumentar primero 4.
D: estructural 20/20.

## Lo que se sostiene

**1. Sin poder ver el sistema, se parchea el síntoma.** Diecinueve de veinte
proponen estabilizar la salida —votando entre reintentos o fijando la
temperatura— cuando no tienen el código. Con el código delante, nueve de veinte.
p = 0,0006. Es el resultado más fuerte del run, y es la tesis en su forma útil:
no hace falta que el agente *diga* que la culpa es del modelo para que *actúe*
como si lo fuera.

**2. La atribución explícita al modelo es minoritaria y marginal.** Cuatro de
veinte sin código, cero con código, p = 0,053. La formulación fuerte —"el agente
culpa al modelo"— no se sostiene ni siquiera con n=20: es el 20% de las
respuestas, no la respuesta por defecto, y el contraste no llega al umbral
convencional por poco.

**3. Nadie pide la información que le falta. Nunca.** Cero de cuarenta pidieron
trazas, logs o datos intermedios antes de diagnosticar, con código y sin él.
Todos dejan la lista de lo que echaron en falta para el final del informe,
después de haber concluido. Es el número más limpio del experimento y no admite
lectura estadística: es 0/40.

## El eje que no esperábamos: el interruptor es del tier medio

Dentro de la condición sin código:

| | tier medio | tier alto | p |
|---|---|---|---|
| Propone tocar la temperatura | **9/10** | **1/10** | 0,0005 |
| Muestreo como causa principal | 4/10 | 0/10 | 0,043 |
| Propone votación o reintentos | 9/10 | 9/10 | 0,76 |

El reflejo de bajar la temperatura es casi universal en el tier medio y casi
inexistente en el alto. Pero **parchear el síntoma con votación no distingue
tiers**: nueve de diez en los dos.

Dicho de otro modo: el modelo más capaz sabe que la variabilidad no viene del
muestreo —no lo dice como causa y no propone tocar la temperatura— y aun así
propone estabilizar la salida con reintentos exactamente igual que el menos
capaz. La diferencia de capacidad se nota en el diagnóstico, no en la conducta.

## Lo que hay que decir en contra

- **La avería es de las fáciles**: determinista, local, reproducible leyendo
  cuarenta líneas. Con el código delante, 20/20 la encuentran. El resultado no
  dice qué pasaría con una avería distribuida o intermitente.
- **El escenario sin código lleva una contrapista**: que 21 de 24 proyectos sean
  estables es en sí mismo un argumento contra el muestreo, y varias respuestas
  lo usaron como tal. Eso deprime la atribución en C y hace el 4/20 un suelo, no
  una estimación.
- **Un solo sistema y una sola avería.** Todo lo anterior describe cómo se
  comportan estos agentes ante este fallo.
- **El sistema es ajeno en las dos condiciones.** La tesis dice "culpa al modelo
  lo que no se culparía a sí mismo", y eso exige que el pipeline sea suyo. Lo
  medido es una asimetría de material, no de autoría.

## Veredicto

El experimento cierra con tres números publicables: **19/20 frente a 9/20** en
parchear el síntoma, **0/40** en pedir la información que falta, y **9/10 frente
a 1/10** en el reflejo de la temperatura entre tiers. La tesis original sobrevive
recortada y desplazada: no es tanto que el agente culpe al modelo como que,
cuando no puede ver el sistema, lo trata como si fuera irreparable y se dedica a
amortiguar su salida.
