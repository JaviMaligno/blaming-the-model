# blaming-the-model

¿Un agente de IA atribuye al muestreo del modelo una variabilidad que en
realidad viene del diseño del sistema? Y si es así, ¿de qué depende?

Este repo contiene el experimento entero: el sistema que falla, las averías, el
arnés que genera los escenarios, los datos crudos de 140 respuestas y el script
que recalcula todos los números publicados.

Artículos: [la observación de la que
salió](https://www.javieraguilar.ai/en/blog/blaming-the-model) y [los
resultados](https://www.javieraguilar.ai/en/blog/patched-the-symptom).

## El resultado, en tres líneas

Se le entrega a un agente un clasificador cuyo lote no devuelve siempre lo
mismo, y se varía **una sola cosa**: si puede ver el código.

| | sin el código | con el código | p |
|---|---|---|---|
| Encuentra la causa | 3/20 | 20/20 | <0,0001 |
| **Parchea el síntoma** (votar o fijar temperatura) | **19/20** | 9/20 | **0,0006** |
| Culpa al muestreo de lo sistemático (2.º escenario) | 6/20 | 0/20 | 0,0101 |
| **Pide la información que le falta** | **0/140** | | |

Ese último no es una errata. Ciento cuarenta respuestas, incluidas cuarenta a
las que el encargo les decía expresamente que pedir datos es una respuesta
completa y que *pedir no es dejar el trabajo a medias*.

## Cómo está organizado

```
src/btm/system/     el clasificador: taxonomía, corpus, búsqueda, presupuesto,
                    contexto, traza. Es lo que se entrega al agente, y no
                    contiene una sola palabra sobre el experimento.
src/btm/variants/   las averías, como módulos alternativos reales (A1..A5).
                    Cada una es una copia de su homólogo con UN cambio.
src/btm/harness/    el arnés: genera escenarios, mide señales, empaqueta,
                    calcula. Nunca se entrega.
data/corpus/        cincuenta repositorios reales de GitHub, capturados con la
                    API. Cola larga, para que ningún modelo los recuerde.
data/scenario/      el corpus del escenario final, con siete pares de proyectos
                    homónimos.
results/            los datos crudos de cada tanda y la estadística.
docs/               las actas: calibración, resultados, y los intentos fallidos.
```

## Reproducir los números

```bash
pip install -e ".[dev]"
pytest                                    # 141 tests, sin red
python src/btm/harness/verify_stats.py    # recalcula todo desde los JSON crudos
```

`verify_stats.py` no depende de ninguna acta: lee los datos crudos y recomputa
cada Fisher exacto y cada intervalo de Wilson. **Si un número de los artículos
no sale de ahí, no está publicado.**

Para regenerar escenarios hace falta un despliegue de Azure OpenAI
(`AZURE_API_BASE`, `AZURE_API_KEY`, `AZURE_API_VERSION`) y un modelo que no
exponga `temperature` — que resultó no ser universal: dentro de una misma
familia, unos despliegues lo rechazan y otros lo aceptan.

## Tres decisiones de diseño que costaron caras

**La avería tiene que ser algo que el modelo demostrablemente no pudo causar.**
Es lo que hace que la clave de corrección no dependa del criterio de quien
puntúa. En el escenario final lo garantiza un hecho aritmético: el mismo
proyecto, pidiendo las mismas secciones, recibe bytes de prompt distintos entre
pasadas. El muestreo no puede cambiar los bytes de un prompt.

**Difícil y determinista tiran en direcciones opuestas.** Tres de los cuatro
rediseños que se propusieron hacían el fallo difícil metiendo concurrencia — y
entonces la entropía venía del servicio de inferencia, con lo que "la
variabilidad viene del modelo" pasaba a ser *verdad* y la rúbrica habría
puntuado un acierto como error. Hay que resolverlo a propósito.

**Cero datos fabricados.** Alcanzar una dificultad intermedia con el código
delante habría exigido inventar metadatos —asignar repositorios a registros de
paquetes que no los listan, escalonar fechas de captura—. Se descartó: un
estudio sobre agentes que toman atajos no puede tomar ése. El defecto vive en la
clave de una caché, no en los datos, y el corpus son copias byte a byte de
repositorios reales.

## Lo que no está aquí

`ground-truth/` está fuera del control de versiones a propósito: contiene las
claves de corrección de cada escenario. Los artículos explican el mecanismo de
cada avería, así que no se oculta nada — pero los paquetes siguen siendo
utilizables por quien quiera repetir la medición con agentes frescos.

## Lo que no se sostiene

Está en `docs/` con el mismo detalle que lo que sí: el brazo con código no
discrimina (20/20 encuentran la primera avería); la forma literal de la tesis
—*lo que no se culparía a sí mismo*— sigue sin medirse, porque en todas las
condiciones el sistema es ajeno; y un hallazgo sobre capacidad del modelo que
parecía sólido con diez respuestas por celda se evaporó al doblar la muestra.
