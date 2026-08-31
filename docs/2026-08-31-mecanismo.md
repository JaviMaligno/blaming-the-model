# De qué se acusa a la cabeza — resultado

Ronda 3. Los mismos dos paquetes de la ronda 2, sin un byte de cambio (260/260
en los dos brazos, diff de una línea verificado por el test que aborta si no).
Cuarenta respuestas nuevas, veinte por brazo, con el prompt literal de la ronda
anterior. Prerregistro en `docs/design/2026-08-31-prerregistro-mecanismo.md`,
comiteado antes de recoger nada.

Textos completos en `results/mecanismo-textos.json` — lo que faltó la vez
pasada. Codificación en `results/mecanismo-codificacion.json`.

## Codificación

Dos codificadores independientes, con particiones desplazadas para que ningún
par de respuestas comparta contexto en las dos pasadas. **Acuerdo en la variable
principal: 38/40 (0,95)**, muy por encima del 0,7 que el prerregistro fijaba
como umbral de invalidación. Los 2 desacuerdos los resolvió un tercero que no
sabía qué había votado cada uno.

## El resultado prerregistrado

| | modelo | bosque | p |
|---|---|---|---|
| **Acusa a la cabeza de aleatoriedad propia** | **14/20** | **4/20** | **0,0018** |

En la dirección declarada de antemano. El criterio era simétrico y las dos
acusaciones estaban ejemplificadas para las dos cabezas.

Mi impresión previa, leyendo las notas de la ronda 2, era más extrema que el
dato: creí ver 12/12 contra 0/6. Medido en limpio es 14/20 contra 4/20. La
asimetría es real y es grande; absoluta no es.

**El vocabulario de la acusación también difiere**, y esto es cualitativo, no
una medida: en el brazo del modelo aparecen «se re-muestrea cada noche»,
«temperature > 0 sin seed», «ruido de muestreo en cada llamada», «la re-tirada
nocturna». En el brazo del bosque, los cuatro que lo acusan no dicen nada
parecido: dicen que **se reentrena sin `random_state`**, que `predict_proba`
corre sobre el lote entero, que el punto flotante se mueve en paralelo. Al
bosque se le acusa de lo que el sistema le hace. Al modelo, de lo que es.

Y los parches siguen al diagnóstico: **proponer fijar la aleatoriedad en la
cabeza, 17/20 contra 11/20** (p = 0,041) — `temperature=0` y `seed` de un lado,
`random_state` y `n_jobs=1` del otro.

## Qué replica de la ronda 2 y qué no

| | ronda 2 | ronda 3 | ¿replica? |
|---|---|---|---|
| Parchea el síntoma | 19/19 | 19/19 | sin diferencia, dos veces |
| Usa el argumento del determinismo | 9/16 p=0,024 | 9/16 p=0,024 | **sí**, idéntico |
| Culpa a la cabeza | 12/6 p=0,055 | 13/6 p=0,028 | **sí**, y ahora significativo |
| Encuentra la causa | 0/4 p=0,053 | 2/8 p=0,032 | **sí** |
| Nombra el mecanismo real | — | 2/8 p=0,032 | nuevo |
| Sitúa la causa aguas arriba | 10/16 p=0,048 | **16/17 p=0,50** | **NO** |
| Pide instrumentación | 0/0 | 0/0 | 0 de 280 |

**La mediación tampoco replica.** En la ronda 2, quien construía el argumento de
exclusión miraba aguas arriba 25/25 contra 1/15, p < 0,0001. En la ronda 3:
22/25 contra 11/15, **p = 0,22**. Era el análisis más bonito que tenía y era
post-hoc; no sobrevive.

## Lo que queda en pie

1. **Parchear es genérico.** 19/20 y 19/20, en las dos rondas, con las dos
   cabezas. Es lo más replicado del proyecto junto al cero.
2. **Nadie pide la información que le falta. 0 de 280.**
3. **La atribución es asimétrica, y replica.** Culpan más a la cabeza (13/20
   contra 6/20), usan menos el argumento que la exculpa (9/20 contra 16/20,
   cifra idéntica en las dos rondas), y sobre todo **la acusan de una naturaleza
   distinta**: 14/20 contra 4/20.
4. **Llegar hasta la causa se mueve**: 2/20 contra 8/20.

## Lo que hay que retirar

**La tesis de «dónde se para la investigación» no aguanta la replicación.**
Mirar aguas arriba salió 10 contra 16 en la ronda 2 y 16 contra 17 en la ronda
3. Con el modelo delante miran aguas arriba exactamente igual; lo que cambia es
que **llegan menos lejos** y que, mientras miran, siguen acusando a la cabeza.

Así que la afirmación que sobrevive es la más antigua y la más simple, la que
estaba en la observación de partida: **al modelo se le atribuye una clase de
fallo que no se le atribuye a un componente equivalente en su lugar** — y con la
misma certificación delante, y con el mismo argumento disponible para exculparlo.

## Lo que hay que decir en contra

- **Una sola avería, un corpus, dos cabezas**, como siempre.
- El codificador **no puede ser cegado**: el texto dice «el modelo» o «el random
  forest» en cada párrafo. Lo que hay en su lugar es un criterio simétrico
  fijado por escrito antes de ver una respuesta, dos codificadores con acuerdo
  de 0,95, y las citas publicadas para que cualquiera discuta cada clasificación.
- **`acusa_via_andamiaje` tiene el acuerdo más bajo** de todas las variables
  (0,80), así que la lectura fina de esa fila es la más floja de la tabla.
- Las dos rondas **no se agrupan**: se reportan por separado y se declara qué
  replica. Agruparlas para ganar potencia sería el atajo que este proyecto mide
  en otros.
