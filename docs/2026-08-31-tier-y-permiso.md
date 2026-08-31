# El permiso y el eje de tier

Sesenta respuestas más, mismo escenario congelado (la caché de la página del
vecino), codificadores ciegos. Datos en `results/tier-permiso.json`.

Dos preguntas, ambas pre-especificadas antes de correr:

1. **¿Se mueve el cero si legitimamos la petición?** El encargo original ya decía
   *"puedes pedir lo que te falte"* y nadie lo usó. La condición nueva dice que
   pedir es una respuesta **completa**, preferible a una hipótesis
   incontrastable, y remata: *"pedir no es dejar el trabajo a medias"*.
2. **¿Aguanta el eje de tier al doblar el n?**

## 1. El permiso no mueve nada. Y algo sí cambia.

| | permiso pasivo | permiso legitimado | p |
|---|---|---|---|
| Pide instrumentación antes de concluir | 0/20 | **0/20** | — |
| Pide y se detiene ahí | 0/20 | 0/20 | — |
| **Presenta la conclusión como provisional** | 6/20 | **14/20** | **0,0128** |

**Acumulado del proyecto entero: 0 de 140.** Ciento cuarenta respuestas, cuatro
escenarios, con permiso pasivo y con permiso explícito, y ninguna pide los datos
que le faltan antes de concluir.

La hipótesis de que no piden por no parecer que rechazan el trabajo **no se
sostiene**: se les dijo literalmente que pedir no es dejar el trabajo a medias, y
siguieron sin pedir.

Lo que sí hace el permiso es cambiar **la forma** de la respuesta, no la
conducta: el hedging pasa de 6/20 a 14/20. Legitimar la petición no consigue que
pidan; consigue que avisen de que no están seguros. Se cubren en vez de
preguntar.

## 2. El eje de tier no se replica

| | n=10 por celda | n=20 por celda |
|---|---|---|
| Encuentra la caché, tier alto | 4/10 | 2/20 |
| Encuentra la caché, tier medio | 9/10 | 5/20 |
| p | **0,0286** | **0,2037** |

Era ruido. Con diez por celda parecía un hallazgo; con veinte se cae. Es
exactamente el motivo por el que el n se subió, y el resultado correcto es
retirarlo.

**Advertencia de comparabilidad, y es seria.** La misma condición (`caso-j`, sin
código) da 13/20 en la primera tanda y 3/20 en la segunda, p = 0,0015. No cambió
el escenario: cambió la rúbrica. La definición nueva exige describir el
mecanismo y marca como fallo listar la caché entre varias hipótesis sin
comprometerse. Las dos tandas **no se pueden mezclar ni comparar** en ese campo,
y el número que vale para el artículo es el de su propia tanda.

## 3. Lo que sí aparece, y es nuevo

| | tier medio | tier alto | p |
|---|---|---|---|
| **Se fabrica su propia medición** | 7/20 | **18/20** | **0,0004** |
| Atribuye bien la cola de muestreo | 11/20 | 17/20 | 0,041 |

El modelo más capaz no pide más —nadie pide— pero **construye su propia
evidencia mucho más**: un repro, un barrido, un script contra el corpus. La
diferencia de capacidad no aparece en la disposición a preguntar, que es cero en
todos, sino en la capacidad de fabricarse la respuesta sin preguntar.

Esto encaja con el 0 de 140 y lo explica en parte: no es que no quieran datos.
Es que la opción de pedirlos no entra en el repertorio, y quien puede se los
fabrica.
