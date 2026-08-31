# Corpus del escenario A5 — documento de arnés

> **Este fichero no se entrega.** Documenta cómo se construyó el corpus y por
> qué está compuesto así; leerlo contesta el escenario entero. Lo que viaja en
> el paquete son los `snapshot.json`, nunca este README. Quien ensamble el
> paquete tiene que copiar el directorio con
> `shutil.copytree(..., ignore=shutil.ignore_patterns("README.md"))` —o el
> equivalente— y comprobarlo después.

51 snapshots: los 8 miembros de cuatro pares de proyectos homónimos y 43
repositorios de relleno. El formato es el mismo de `data/corpus/`, el que define
`src/btm/system/corpus.py`, y los snapshots son válidos y autoconsistentes uno a
uno. Captura del 2026-08-31, 652 documentos, 22 de los 51 sin descripción.

## Cómo se capturó

Con `btm.harness.ingest.capture(..., short_name_urls=True)`. Ese modo identifica
cada documento por el nombre corto del repositorio (`repo.name`) en lugar de por
el completo (`repo.full_name`):

```
https://github.com/pinterest/orion#0   →   https://github.com/orion#0
```

Es un descuido de captura de los que se cometen solos, y sobre dos proyectos
distintos que se llaman igual produce las mismas URLs. Ningún snapshot delata
nada por sí mismo: la colisión sólo existe **entre** dos ficheros, y hay que
cruzar las URLs de todo el corpus para verla. Esa es, deliberadamente, la única
vía por la que el dato la enseña.

El resto de la captura no cambia: `slug`, `source_url` y `captured_at` siguen
diciendo de qué repositorio salió cada snapshot.

## Los cuatro pares

Salen de la Fase 0 (`results/fase0-pares.json`, 514 clasificaciones reales), que
midió dos cosas por par: que ambos miembros clasifican igual las cinco veces en
solitario, y que la víctima cambia de etiqueta cuando se le sirve la
documentación del donante. La dirección no es simétrica salvo en `orion`, así
que la víctima está elegida, no es intercambiable.

| nombre | donante | etiqueta | víctima | etiqueta | URLs compartidas |
|---|---|---|---|---|---|
| orion  | `pinterest--orion`         | infra.orchestration | `orion-rs--orion`     | devtools.libraries  | 8 |
| badger | `outcaste-io--badger`      | data.storage        | `badger-cash--badger` | business.payments   | 6 |
| atlas  | `karam-ajaj--atlas`        | infra.networking    | `yoonic--atlas`       | business.payments   | 5 |
| sentry | `jasonrichardsmith--sentry`| infra.orchestration | `samueleaton--sentry` | devtools.build      | 8 |

Los ocho miembros son idénticos, documento a documento, a los de `data/pairs/`
salvo en la URL: lo que midió la Fase 0 sigue valiendo tal cual.

Las URLs compartidas no son adorno: todas las que entran en la ventana de
contexto de cada víctima son compartidas (3/3, 4/4, 3/3 y 3/3 respectivamente),
medido sin gastar una sola llamada al modelo con `query_plan` + `ToolBox.search`
del sistema sano.

## Que no colisione nada más

`python -m btm.harness.scenario_corpus audit` cruza las URLs de los 51
snapshots y separa las colisiones declaradas de las accidentales. Estado actual:

```
shared_within_pair  orion 8 · badger 6 · atlas 5 · sentry 8   (mínimo exigido: 3)
stray               {}
missing             []
```

Cero colisiones fuera de los pares, ni entre repositorios de relleno ni entre
uno de relleno y un miembro de par. Toda ampliación del corpus tiene que volver
a pasar por aquí.

## Cribado de estabilidad

**El criterio.** Un repositorio que responde distinto de una corrida sana a otra
es indistinguible de uno contaminado. Sin cribarlo, la afirmación de la que
cuelga la medición —«todo cambio de etiqueta observado es una corrida
contaminada»— deja de ser un hecho y se vuelve discutible. Así que: cada
repositorio de relleno se clasificó **5 veces con el sistema sano** (gpt-5-mini,
`btm.system.classifier.classify`, sin variante de por medio) y se exige
unanimidad. Mayoría no basta.

**El resultado.** De los 50 repositorios de `data/corpus/`:

- **3 fuera antes de empezar**, ya condenados por el gate de calibración
  (`results/gate.json`): `harumiWeb--xlflow`, `jacovinus--snoutdb`,
  `Radiergummi--cetacean`.
- **47 cribados**, 235 clasificaciones. **43 unánimes, 4 caídos**:

  | repositorio | códigos en 5 corridas |
  |---|---|
  | `Alexli18--binex`            | infra.orchestration ×4, ai.agents ×1 |
  | `jeyben--fixedformat4j`      | devtools.libraries ×3, data.pipelines ×2 |
  | `josephleblanc--ploke`       | devtools.libraries ×4, ai.agents ×1 |
  | `vector-index-bench--vibe`   | devtools.testing ×3, ai.serving ×1, data.storage ×1 |

  Detalle corrida a corrida en `results/scenario-cribado.json`, que guarda los
  47, no sólo los descartados.

Total: **43 de relleno + 8 de pares = 51**. Los siete inestables conocidos están
listados en `UNSTABLE`, en `src/btm/harness/scenario_corpus.py`, para que una
reconstrucción no los vuelva a meter.

Los pares no pasan por este cribado porque la Fase 0 ya se lo hizo, con el mismo
criterio de unanimidad sobre 5 corridas.

## Dos cosas que se heredaron a propósito

- **La descripción ausente.** El criterio de `data/corpus/` pide repositorios con
  descripción y sin ella en proporción parecida, y para conseguirlo 16 capturas
  se hicieron con `keep_description=False`. La recaptura hereda esa decisión
  repositorio a repositorio; si no, devolvería la descripción a un tercio del
  corpus y cambiaría el plan de consultas del clasificador, que pregunta de más
  cuando no la hay.
- **La deriva del material real.** Tres repositorios cambiaron su README entre la
  captura de `data/corpus/` (2026-08-30) y ésta: `colliery-io--cloacina` (1
  documento), `lance0--rustbgpd` (3) y `rknightion--tailscale2otel` (3). Los tres
  pasaron el cribado con el texto nuevo, que es el que está aquí. Ninguno de los
  ocho miembros de par derivó.

## Reconstrucción

```bash
python -m btm.harness.scenario_corpus capture   # recaptura los 51 snapshots
python -m btm.harness.scenario_corpus audit     # cruza las URLs de todos
python -m btm.harness.scenario_corpus screen    # 5 corridas sanas por repo
```

`capture` necesita `gh` autenticado; `screen`, las credenciales del despliegue
(`source ~/Documents/repos/CooperBench/azure_env.sh`). `audit` no gasta nada y
debería correrse después de cualquier cambio en el corpus.
