# Prerregistro — de qué se acusa a la cabeza

Escrito y comiteado **antes** de recoger ninguna respuesta de esta ronda.
Motivo: en la ronda v2 observé, leyendo las notas de codificación, que el
mecanismo que los agentes atribuyen a la cabeza parece distinto según qué cabeza
sea. Esa observación es post-hoc, mía, no ciega y sobre notas y no sobre textos.
No es publicable. Esta ronda la mide de cero.

## Pregunta

Cuando un agente responsabiliza a la cabeza clasificadora de una variabilidad
que en realidad viene de aguas arriba, **¿de qué la acusa?**

- **Intrínseco**: sostiene, como causa viva, que la cabeza produce salidas
  distintas ante la misma entrada por su propia naturaleza — muestrea, tiene
  ruido, es estocástica, «tira el dado».
- **Extrínseco**: sostiene que la cabeza es determinista y que la variabilidad
  viene de lo que el sistema le hace — la reentrena, la reconstruye, la
  paraleliza, le cambia la configuración o el artefacto.

Las dos acusaciones son formulables contra las dos cabezas. Un modelo de
lenguaje puede ser acusado de extrínseco (el servidor agrupa peticiones, la
configuración cambia); un bosque puede ser acusado de intrínseco (los árboles
votan con aleatoriedad, el paralelismo mueve el punto flotante). El diseño no
favorece a ninguna combinación.

## Hipótesis

**H1 (principal).** El brazo del modelo de lenguaje acusa a su cabeza de
aleatoriedad intrínseca con más frecuencia que el brazo del bosque.

Dirección declarada antes de mirar: modelo > bosque. Test de Fisher exacto de
una cola. Umbral 0,05. Si sale al revés o no alcanza, se publica igual.

## Variables

Sobre las 20 respuestas de cada brazo, no sólo sobre las que culpan a la cabeza.

1. **`acusa_aleatoriedad_intrinseca`** (principal). La respuesta sostiene como
   causa viva —no como hipótesis que ella misma descarta— que la cabeza da
   salidas distintas ante la misma entrada por su propia naturaleza.
2. **`acusa_via_andamiaje`**. Sostiene como causa viva que la variabilidad de la
   cabeza viene de algo que el sistema le hace.
3. **`propone_fijar_la_cabeza`**. Propone eliminar aleatoriedad en la cabeza:
   `temperature=0`, `seed`, `random_state`, `n_jobs=1`, votar sobre k muestras.
4. **`nombra_el_mecanismo_real`**. Nombra orden de recuperación dependiente de
   la petición, o `PYTHONHASHSEED` / orden de iteración por proceso.

Se recodifican además las cinco variables de la ronda v2 con las mismas
definiciones, para comprobar que la tabla replica.

## Procedimiento

- Los **mismos dos paquetes** `v2-llm` y `v2-rf`, sin un byte de cambio. Difieren
  en una línea y el test que lo comprueba sigue activo.
- **n = 20 por brazo**, respuestas nuevas. Sin parada opcional: se recogen las 40
  y se analizan las 40.
- **Los textos completos se guardan** en `results/mecanismo-textos.json` antes de
  codificar. Ése fue el fallo de la ronda anterior: sin textos no se puede
  recodificar nada.
- **Doble codificación independiente** de cada respuesta, por dos codificadores
  que no ven el juicio del otro. Se reporta el acuerdo y todos los desacuerdos.
  Los desacuerdos se resuelven con un tercer codificador y se declaran.
- El codificador **no puede ser cegado al brazo** —el texto habla de «el modelo»
  o de «el random forest» en cada párrafo— y fingir lo contrario sería mentir.
  Lo que se hace en su lugar: el criterio de arriba es simétrico y está fijado
  por escrito antes de ver una sola respuesta, y se publican las citas de cada
  clasificación para que cualquiera pueda discutirla.

## Qué invalidaría el resultado

- Que los dos BRIEF difieran en más de una línea (el test aborta la corrida).
- Que el acuerdo entre codificadores en la variable principal sea inferior a 0,7.
- Que alguna de las dos acusaciones resulte no formulable contra alguna de las
  cabezas al leer las respuestas — sería un defecto de simetría del criterio, y
  se declara.
