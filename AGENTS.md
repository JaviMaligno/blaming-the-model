# AGENTS.md — blaming-the-model

Experimento: ¿un agente de IA atribuye al muestreo del modelo una variabilidad
que en realidad viene del diseño del sistema? El repo contiene el sistema que
falla, las averías, el arnés que genera los escenarios, los datos crudos y el
script que recalcula todos los números publicados. Contexto completo en
`README.md`; las actas (calibración, resultados, intentos fallidos) en `docs/`.

Repo público (GitHub). Documentación, commits y docstrings en español.

## Estructura

```
src/btm/system/     el clasificador sano (taxonomía, corpus, búsqueda,
                    presupuesto, contexto, traza). Es lo que se ENTREGA al agente.
src/btm/variants/   las averías A1..A5 (+ CACHED, RF): copias de un módulo
                    sano con UN solo cambio cada una.
src/btm/harness/    el arnés: genera escenarios, pasadas, señales, paquetes y
                    estadística. NUNCA se entrega.
data/               corpus de repos reales de GitHub (copias byte a byte),
                    escenario, taxonomía, juicios.
results/            datos crudos de cada tanda, `estadistica.txt` y los
                    manifiestos de integridad `frozen*.json`.
docs/               actas y diseño (`docs/design/`, `docs/calibration/`).
tests/              pytest, sin red.
```

## Comandos

```bash
pip install -e ".[dev]"                   # Python >= 3.12
pytest                                    # toda la suite, sin red
python src/btm/harness/verify_stats.py    # recalcula la estadística desde los JSON crudos
```

Módulos del arnés con CLI propia (ver el docstring de cada uno para sus
argumentos):

```bash
python -m btm.harness.cli scenario --variant A4 --repo <slug> --out out/
python -m btm.harness.cli judgement --set B1 --out out/
python -m btm.harness.guardian all --runs results/guardian --out results/guardian.json
python -m btm.harness.answers build --runs results/guardian --arm model
python -m btm.harness.guardian_case_v2 --cases <dir>
```

Otros con `argparse`: `gate`, `passes`, `batch`, `rf`, `a5_report`, `fitness`.

Generar escenarios nuevos requiere un despliegue de Azure OpenAI vía variables
de entorno (`AZURE_API_BASE`, `AZURE_API_KEY`, `AZURE_API_VERSION`; en
`btm/harness/model.py` tienen prioridad `BTM_AZURE_ENDPOINT`, `BTM_AZURE_KEY`,
`BTM_API_VERSION`, y el despliegue se elige con `BTM_DEPLOYMENT`) y un modelo
que no exponga `temperature`. Las credenciales se leen del entorno y nunca se
escriben a disco.

## Reglas que no se rompen

- **El sistema entregado no puede delatar el experimento.** Nada en
  `src/btm/system/` ni en `src/btm/variants/` puede mencionar avería, bug,
  escenario, experimento o variante (`tests/test_variants.py` lo vigila en
  `variants/`). Lo que explica el experimento va en el arnés.
- **Una variante = su homólogo sano + un cambio.** `materialise` copia el árbol
  sano y sustituye sólo los módulos de la variante; los tests comprueban que
  el resto queda idéntico.
- **Guards y lógica de medición viven en el arnés**, no en el sistema (p. ej.
  el guard de temperatura está en `btm/harness/model.py`, no en
  `btm/system/model.py`).
- **Cero datos fabricados.** El corpus son capturas reales; los defectos viven
  en el código, nunca en los datos.
- **Si un número no sale de `verify_stats.py`, no se publica.** Cualquier cifra
  nueva en docs o artículos tiene que poder recomputarse desde `results/`.
- **Las pasadas dependen de `PYTHONHASHSEED`**: `passes` falla si la variable
  no coincide con `--seed`. Cada pasada se lanza en su propio proceso.
- **No tocar los paquetes congelados.** `results/frozen*.json` guarda el
  SHA-256 de cada fichero de los escenarios para demostrar que no se
  modificaron tras ver resultados.

## Ficheros fuera de git

`.gitignore` excluye `ground-truth/` (claves de corrección de cada escenario,
a propósito), `.work/` (paquetes y corridas de trabajo) y `out/`. No añadirlos
al control de versiones.

## GitGuardian

`.gitguardian.yaml` excluye `data/**` (READMEs de terceros con ejemplos de
contraseñas) y `results/frozen*.json` (hashes). `src/`, `tests/`, `docs/` y la
configuración siguen vigilados: no meter secretos ahí.
