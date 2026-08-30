# Congelación de escenarios

Fecha: 2026-08-31. Commit del sistema: `282489f`.

A partir de aquí, escenarios, prompts y rúbrica quedan fijos. El run de
confirmación corre sobre este conjunto y se reporta lo que salga.

| escenario | condición | ficheros | digest |
|---|---|---|---|
| `caso-f` | C — varianza sin código | 3 | `5fc1893dee753499` |
| `caso-g` | D — varianza con código | 10 | `33c8686e047c5e73` |

Manifiesto por fichero en `results/frozen.json`.

## Qué NO entra en el run de confirmación

Las 32 respuestas de la calibración (`results/calibracion.json`) se quedan donde
están y **no se mezclan** con las de confirmación. Se recogieron con dos rúbricas
distintas —la de C no distinguía entre bajar la temperatura para reducir la
varianza y usarla para medir confianza, y la de D sí— y con el escenario de C
todavía contaminado por un fichero sobrante que actuaba como pista.

Mezclarlas para engordar el n sería exactamente la clase de atajo que este
experimento se dedica a medir en otros.

## El run de confirmación

- Veinte respuestas por condición, mitad de tier alto y mitad de tier medio.
- Una sola rúbrica, la de la condición D, que es la estricta.
- Se reporta el resultado salga como salga, incluido un nulo.
