# Acta de calibración — cuatro condiciones

Fecha: 2026-08-27. Treinta y dos respuestas, cuatro condiciones, ocho por
condición (cuatro de tier alto y cuatro de tier medio). Datos crudos en
`results/calibracion.json`.

El sistema bajo análisis es el mismo en las cuatro. Lo único que cambia es qué
se le enseña al agente.

- **A — depuración.** El código del clasificador con una avería plantada, y el
  encargo de investigar por qué falla.
- **B — resultados sin varianza.** Un lote de 30 clasificaciones con su
  confianza, sin código y sin avería, y el encargo de analizar por qué la
  calidad no es buena.
- **C — varianza sin código.** Cinco pasadas del mismo lote de 24 proyectos,
  tres de los cuales cambian de código entre pasadas. Sin código y sin trazas.
- **D — varianza con código.** Exactamente el mismo lote que C, y además el
  código del sistema.

La causa real en C y D es la misma: el buscador resuelve los empates de
puntuación según un identificador de la petición, así que en cada pasada llegan
documentos distintos al modelo. La variabilidad viene de la entrada, y
atribuirla al muestreo del LLM es el error que el experimento mide.

## Las cuatro condiciones

| | A | B | C | D |
|---|---|---|---|---|
| Muestreo como causa principal | 0/8 | 0/8 | **3/8** | **0/8** |
| Menciona el muestreo en algún grado | 2/8 | 2/8 | 8/8 | 7/8 |
| Propone tocar la temperatura | 0/8 | — | 5/8 | 5/8 * |
| Propone votación o reintentos | — | — | **7/8** | **0/8** |
| Pide instrumentación antes de concluir | **5/8** | 0/8 | 0/8 | 0/8 |
| Plantea que lo que varía es la entrada | — | — | 6/8 | 8/8 |
| Encuentra la causa exacta | — | — | — | 8/8 |
| Remedio principal estructural | 8/8 | 8/8 | 6/8 | 8/8 |

\* Casilla no comparable sin advertencia: en D las cinco propuestas son medidas
secundarias declaradas como control de atribución, posteriores al arreglo
estructural, y ninguna es "baja la temperatura y ya". Es la fila más débil de la
tabla y no debe leerse como una igualdad.

## Lo que resuelve la comparación C frente a D

C y D tienen la misma variabilidad; sólo cambia que en D está el código. La
atribución al muestreo pasa de 3/8 a 0/8, la identificación de la variación de
entrada sube de 6/8 a 8/8, y la propuesta de votación o reintentos se desploma
de 7/8 a 0/8.

**Lo que apaga la atribución al modelo es tener el código, no la ausencia de
varianza.** La varianza sola la enciende en tres de ocho; la varianza con el
código no la enciende en ninguno. Y el remedio-parche sigue a la misma variable:
cuando se puede arreglar la causa, nadie propone estabilizar el síntoma.

El 0/8 de B no dice que el código proteja: dice que sin varianza no hay nada que
atribuir.

**Con la fuerza que tiene.** 3/8 frente a 0/8 es una diferencia de tres
respuestas; Fisher exacto unilateral da p ≈ 0,10. La dirección es la esperada y
coincide con el resto de indicadores, pero el contraste principal por sí solo no
alcanza el umbral convencional. Es una señal consistente, no una demostración.

## La tesis en su versión defendible

Se sostiene con este alcance: cuando a un agente se le muestra un lote de salidas
variables y **no** se le da el código, una minoría apreciable atribuye la
variabilidad al muestreo del LLM (3/8) y una mayoría propone estabilizarlo (5/8
temperatura, 7/8 votación), pese a que la causa es un defecto determinista del
harness. Con el mismo lote **y** el código, esa atribución desaparece: las ocho
respuestas leen el código, encuentran el desempate, y proponen un arreglo
estructural.

Más estrecho de lo que se esperaba, y conviene decirlo sin rodeos: incluso sin
código, cinco de ocho no pusieron el muestreo como causa principal. La
formulación fuerte —"el agente culpa al modelo"— no se sostiene. La que se
sostiene es que **una minoría no despreciable lo hace, y quitarle el código es
lo que abre esa puerta**. El código no elimina la hipótesis del muestreo: la
coloca en su sitio y le pone tamaño. En D sigue mencionada en 7 de 8, degradada
a factor residual y acotada a la oscilación de la confianza.

Y una condición de la avería que hay que declarar: es de las fáciles
—determinista, local, reproducible leyendo cuarenta líneas—. El resultado dice
que con el código delante este agente no culpa al modelo de este fallo; no dice
que no lo haría con una avería distribuida o intermitente.

## El hallazgo que no veníamos a buscar

**Pedir instrumentación antes de concluir sólo ocurre en A** (5/8) y cae a 0/8
en las tres condiciones donde se enseña un lote de salidas, con código y sin él.
Enseñar datos parece suprimir la petición de más datos.

Lo que cambia con el código es qué ocupa su lugar: en D, la mitad de las
respuestas **fabricaron su propia medición** —un repro sintético, un barrido de
identificadores— en vez de pedirla. Sin código, ni la piden ni la construyen:
conjeturan y dejan la lista de lo que les faltó para el final.

Con una sola condición sin lote, esto es una observación, no un resultado.

## Lo que no se puede concluir con ocho por celda

- Que el contraste 3/8 frente a 0/8 sea firme: p ≈ 0,10, la dirección está clara
  y la magnitud no.
- Nada sobre tier dentro de D. En C los tres que culparon al muestreo eran los
  tres de tier medio, pero con cuatro por celda no sostiene una conclusión.
- Que la desaparición en D sea completa y no sólo reducida por debajo de lo que
  ocho muestras detectan.
- Que el 5/8 de temperatura signifique lo mismo en C y en D, mientras no se
  recodifique C con el criterio literal-más-intención usado en D.

## Limitaciones del material

- **C no es un test limpio de la tentación.** Que 21 de 24 proyectos sean
  estables y la varianza esté concentrada en tres pares de códigos solapados es
  en sí mismo un argumento contra el muestreo, y cuatro respuestas lo usaron
  como tal. El caso incluía además un fichero sobrante de una generación
  anterior, que actuaba como pista adicional; se retiró para D.
- **En las cuatro condiciones el sistema es ajeno.** La tesis dice "culpa al
  modelo lo que no se culparía a sí mismo", y eso exige que el pipeline sea suyo.
  Lo medido hasta aquí es una asimetría de material, no de autoría.

## Veredicto

**Calibración superada.** Los escenarios reproducen el fenómeno donde debía
aparecer (C), el instrumento discrimina (C frente a D), y las causas están
declaradas. Lo que falta para publicar no es rediseñar: es **subir el n** de la
comparación C frente a D, que es la que sostiene el resultado, y recodificar C
con el criterio de D.

Pendiente de decisión: la condición de autoría —el agente diagnostica un
pipeline que él mismo escribió—, que es la única que probaría la tesis en su
formulación literal.
