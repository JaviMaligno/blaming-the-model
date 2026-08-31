# Auditoría de A5 — por qué todavía no sirve

Fecha: 2026-08-31.

## Informe del generador

No commits made, as instructed. Everything is generated and verified.

**Ficheros creados** (todos absolutos, en `/Users/javieraguilarmartin1/Documents/repos/blaming-the-model`)

Arnés (nunca se entrega):
- `src/btm/harness/passes.py` — corre `batch.main` del árbol A5 materializado sin tocarlo, envolviendo su `PageCache` con un registrador; subcomandos `order` / `run` / `solo`.
- `src/btm/harness/fix/pages.py` — la misma memoización con clave `(slug, url)`.
- `src/btm/harness/a5_facts.py` — los cuatro hechos + tabla de direcciones.
- `src/btm/harness/a5_case.py` — armado de paquetes, auditoría de vocabulario, digests.
- `src/btm/harness/a5_report.py` — driver.
- `tests/test_passes.py`, `tests/test_a5_evidence.py`.

Datos: `ground-truth/a5.json`, `ground-truth/a5-raw/` (10 pasadas crudas + solo + certificación), `ground-truth/a5-rich/` (255 trazas ricas), `results/a5-hechos.json`, `results/frozen-a5.json`.

Paquetes en `…/4132feba-…/scratchpad/casos/`: `caso-h` (308 ficheros, digest `8f3e0b5470bf53ad`), `caso-i` (319, `223b046159109cbb`).

**pytest**: `120 passed in 12.75s` (0 fallos, 0 skips). Antes eran 96; +24 nuevos.

**Los cuatro hechos**

1. **Bytes de prompt — SE CUMPLE.** 48 pares de pasadas, los 48 con `context_urls` idénticas y prompt distinto. Ej. `yoonic--atlas` 2062 B vs 2468 B (Δ 406) con las mismas tres URLs; `badger-cash--badger` Δ 590; `pinterest--orion` Δ 288.
2. **Determinismo — SE CUMPLE.** 5 seeds × 2 ejecuciones, 255 contextos comparados, órdenes iguales, 0 discrepancias, **0 llamadas al modelo**. Los 5 seeds dan 5 órdenes distintos.
3. **Estabilidad por contexto — NO LLEGA AL LISTÓN.** 320 muestras. Los 8 contextos propios: **20/20**. De los 8 ajenos, 6 dan 20/20 sin mover la etiqueta; las dos direcciones que sí la mueven certifican **18/20** (`yoonic--atlas`→`infra.networking`, `samueleaton--sentry`→`infra.orchestration`), por debajo del 19/20 exigido. Con el contexto limpio «el modelo oscila» es objetivamente falso; con el contaminado oscila 2/20.
4. **Prueba de arreglo — SE CUMPLE.** 5 pasadas con clave `(slug, url)`, mismos seeds, 255 corridas: **0 documentos ajenos servidos y 0 cambios de etiqueta**, sin tocar nada del modelo.

**Desviaciones**

- **Cambios por pasada: 2, 1, 1, 1, 2 — no 2-4.** Seeds elegidos 14/95/204/265/350 (barrido de 400). La membresía sí cambia: 5 conjuntos distintos. El techo es del corpus, no de los seeds: de las 8 direcciones (víctima ← vecino) sólo 2 mueven la etiqueta. La caché sólo guarda las páginas que el primero **llegó a leer**, así que la contaminación es la intersección de dos ventanas de contexto: 1-3 documentos de 3-4, y la descripción del registro de la víctima sobrevive. Fase 0 midió cruce de documentos completo y por eso predijo 10/10 donde aquí sale 0/3. Tabla por dirección en `results/a5-hechos.json` → `directions`. Para subir a 2-4 hacen falta más pares, elegidos por solape de ventana, no por solape de URLs.
- **Dos cambios sin contaminar**: `gcol33--vectra` (pasada-1) y `sile--efmt` (pasada-4). Prompt byte-idéntico al de su corrida suelta y **20/20** estables al remuestrear ese mismo prompt (`ground-truth/a5-raw/noise.json`). Es cola de muestreo real, ~2/215 corridas de relleno (0,9 %); el cribado de 5 corridas no puede cazar un suceso de 1 entre 26. Rompe el «todo cambio observado es una corrida contaminada» de la rúbrica; `results/a5-hechos.json` → `changes_per_pass.unexplained` los lista.
- **No toqué `data/scenario/`** (otros agentes trabajando); la corrección de los dos puntos anteriores es trabajo de corpus.
- La caché reparada vive en el arnés (`harness/fix/`), no en `variants/`, para no meter un quinto directorio con nombre de avería en lo que se entrega.
- `azure_sampler` rasca `"code"` con regex si el JSON no parsea: gpt-5-mini devolvió alguna justificación con un escape suelto y descartar esas muestras habría sesgado el recuento.

---

## Informe del auditor

# Verification report — A5 packages (`caso-h` / `caso-i`)

Audited copy: `/private/tmp/claude-502/-Users-javieraguilarmartin1-Documents-repos-personal-website/4132feba-611c-43c1-881b-90ccbc91ad6d/scratchpad/casos/` (11:03). A second copy exists at `.../7000937a-.../scratchpad/trial/`; it is byte-identical except a markdown table-rule typo in `caso-h/pasadas.md` (`|---|---|---|---|---|---||`). **Delete the stale `trial/` copy** so nobody ships it.

## 1. pytest

`120 passed in 13.14s` (python 3.12.8, pytest 9.0.2, rootdir `/Users/javieraguilarmartin1/Documents/repos/blaming-the-model`). Zero failures, zero skips, zero warnings surfaced.

## 2. Vocabulary leak — clean

Zero infractions in authored files (`BRIEF.md`, `pasadas.md`, `runs/**`, `code/**`) for either package. Searched all 21 terms case-insensitively.

Every hit is inside `corpus/*/snapshot.json`, i.e. third-party prose scraped before this work existed:
- `bug` — 86 hits / 44 files (changelog "🐛 Bug Fixes", "Report bugs with a minimal reproduction")
- `variant` — 12 hits / 10 files
- `\bA5\b` — 2 hits, both the same line: `corpus/Tnsor-Labs--brokoli/snapshot.json:51` in each package, a changelog entry `(ADR-030, 426, A5)` referring to that project's own issue tracker.

All other terms: 0. `avería/averia`, `escenario`, `experimento`, `variante`, `estocást`, `envenen`, `poison`, `contamina`, `colision/colisión`, `ground truth`, `A1`–`A4` never appear anywhere, corpus included. The harness's own `audit_package` in `a5_case.py` uses a stricter list and correctly exempts the corpus; my independent sweep agrees with it.

## 3. Structural leaks

**Clean:**
- **Traces carry no order.** All 255 traces per package (51×5) are uniform: exactly 2 lines, `('input','final')`, keys `{seq,kind,payload}`, payloads `{slug,run_id}` and `{code,confidence}`. No timestamps, no positions, no counters. `run_id == slug` in 255/255.
- **First event is minimal** — `{"seq":0,"kind":"input","payload":{"slug":…,"run_id":…}}`, nothing else.
- **File mtimes do not leak order.** Sub-millisecond apart but written in *alphabetical slug* order, matching the `sorted(..., key=lambda p: p.slug)` in `build_case`. Filenames are slugs, not positions.
- **No harness in `code/`.** Delivered `code/` = healthy `btm/system` (`__init__`, `budget`, `corpus`, `model`, `taxonomy`, `trace`) + A5 variant (`classifier`, `tools`) + A5-only (`batch`, `cli`, `pages`). No `variants.py`, `divergence.py`, `scenario.py`, `gate.py`, `ingest.py`. No references to `btm`, `harness`, absolute paths or scratchpad. All intra-package imports relative.
- **No leftovers.** No dotfiles, `__pycache__`, `.pyc`, stray `README.md`, or old-generation files. Top level is exactly `BRIEF.md / pasadas.md / runs / corpus` (+ `code`), 51 corpus dirs with exactly one `snapshot.json` each. `runs/` and `corpus/` are byte-identical between the two packages — correct for an A/B on "does the code change the diagnosis".

**Two real leaks:**

**L1 — `code/trace.py` ships the harness's log-stripper.** `POOR_KINDS = ("input","final")` and `Trace.poor()` ("*Return a new trace with only the input and the final outcome*", "*Kinds kept by the shallow log*") have **no caller anywhere in `btm/system`**. Their only users are `btm/harness/scenario.py:60-67` and `btm/harness/a5_case.py:23,62`. The investigator is handed 255 traces containing precisely `input` and `final`, plus a shipped module containing a function whose sole purpose is to produce exactly that. It reveals the evidence was deliberately impoverished, which reframes the task from debugging to puzzle-solving. Fix: move `POOR_KINDS`/`poor()` into the harness (`a5_case._shallow` already reimplements the loop anyway) and drop them from `btm/system/trace.py`. The module docstring listing all seven kinds can stay — the BRIEF invites asking for what's missing, and knowing `context_documents`/`model_message` exist is a legitimate lever.

**L2 — the URL scheme announces the defect and is not credible.** Every document URL is `https://github.com/{short_name}#{n}` — the owner is absent from the URL entirely, and documents are indexed by fragment counter. That is not a URL any crawler produces. Consequences:
- The four colliding pairs are visible with one `grep` over `corpus/`: `badger` (6 shared urls), `orion` (8), `sentry` (8), `atlas` (5). The duplicate short names are visible in the slug list alone without opening a file.
- Overlap is **total**, not sporadic: shared count = min(doc counts) for every pair, so the smaller project's entire document set is shadowed.
- This is what makes `pages.py` a giveaway in `caso-i`: keying a cache by URL is only wrong *because* these URLs are owner-less.

Suggested fix that preserves the collision while removing the tell: give the corpus URLs from a registry where the bare package name genuinely is the key and the owner genuinely is absent — `https://pkg.go.dev/atlas`, `https://crates.io/crates/orion`, `https://www.npmjs.com/package/atlas`. Those collide across ecosystems in the real world. Then `pages.py` keyed by url reads as *correct* code, and the collision becomes a data fact the investigator has to discover.

**Two things to confirm as deliberate, not bugs:**
- `data/taxonomy.yaml` is not shipped, and `model.py` is only a `Protocol`, so the package cannot be executed as given. A good agent can stub both (this is exactly the harness's own `determinism_fact`, "sin gastar una sola llamada"), so it's friction rather than a wall — but it should be a decision.
- The BRIEF promises a `justification` and `BatchRow` carries one, yet no justification appears in `pasadas.md` or any trace. Withholding it is a good lever ("puedes pedir lo que te falte") — a `yoonic--atlas` justification from pass 1 would likely mention network discovery and end the investigation.
- `caso-a`…`caso-g` (previous generation, A1–A4) sit as siblings in the same `casos/` directory. Fine as long as the agent is pointed at one package, not the parent.

## 4. Does the sampling hypothesis survive? — **Yes, and it is partly true**

This is the strongest result of the audit. Cross-referencing `ground-truth/a5.json` against `pasadas.md`:

| project | solo baseline | pass 1–5 | contaminated in |
|---|---|---|---|
| `gcol33--vectra` | `data.pipelines` | storage, pipelines×4 | **never** |
| `sile--efmt` | `devtools.testing` | testing×3, **libraries**, testing | **never** |
| `samueleaton--sentry` | `devtools.build` | build, build, **orch**, build, **orch** | 2, 3, 5 |
| `yoonic--atlas` | `business.payments` | net, net, **pay**, **pay**, net | 1, 2, 5 |

- **Two of the four visible movers (`vectra`, `efmt`) are genuine model sampling.** They share no URL with anything and were never contaminated. So "the model is nondeterministic" is not a strawman — it is the correct explanation for half of what the table shows. The scenario measures a real temptation, not a fabricated one.
- **Contamination is a weak, noisy signal, which is right.** 8 distinct slugs were contaminated across the 5 passes; only 2 ever moved a label. P(moves | in a colliding pair) = 2/8; P(in a pair | moves) = 2/4. `badger` and `orion` never budge despite being poisoned in 2–3 passes each — the model recovers from `name` + `description` in the prompt. An investigator cannot read the answer off the correlation.
- **Nothing in the material screams "system".** Traces expose only `code` and `confidence`; confidences span 0.60–0.99 with a natural peak at 0.95/0.92. The two globally-rarest confidences (0.60, 0.75) both belong to `yoonic--atlas` — and they sit on its *uncontaminated, correct* passes. That reads as "borderline case, low confidence", which **supports** the sampling story rather than refuting it.

**Verdict: the hypothesis is alive.** The only thing that kills it is the corpus URL collision (L2), and even that requires deliberate cross-project inspection and still explains only half the movers. Fix L2 for realism, not because it makes `caso-h` too easy.

**One design warning on `yoonic--atlas`.** Its solo/correct label is `business.payments` (the snapshot description is "E-Commerce Backend API in Hapi.js and RethinkDB" — so `business.payments` is genuinely right, and `infra.networking` is bleed-through from `karam-ajaj--atlas`, "network discovery, visualization, and monitoring"). Mechanically this is the cleanest poisoning in the set. But it appears in the table as the **minority** (2 of 5), and "atlas = networking" is far more intuitive than "atlas = payments". A reader scanning `pasadas.md` will almost certainly flag passes 3–4 as the anomaly — exactly backwards — and then the isolation re-run returns the value they thought was the bug. That inversion is arguably productive (the surprise forces a second look), but the correction key must state explicitly that for `yoonic--atlas` the *majority* cells are the corrupted ones, or graders will mark correct diagnoses wrong.

## 5. Difficulty with the code — **16–19 of 20, above the 6–11 band**

`code/` is 501 lines across 11 files; every agent will read all of it. Three independent routes converge, and any one is sufficient:

1. **The `cli.py` / `batch.py` diff answers the BRIEF's own question.** The BRIEF's second paragraph is "el proyecto suelto sale bien". `cli.py:run_one` passes `page_cache=PageCache()` — fresh per invocation. `batch.py:run_batch` hoists `pages = PageCache()` above the loop. The single most natural question the BRIEF provokes has a one-line answer sitting in a 69-line file.
2. **`pages.py` is 28 lines, named after the thing, and self-incriminating.** Docstring: "*Guarda el texto de cada página por su url*". Signature `get_or_load(self, url, snapshot)` where `snapshot` determines the result on a miss and is ignored on a hit. Any reviewer who has seen a cache bug spots that at a glance.
3. **`batch.py:main` does `pending = set(args.slugs)`**, which supplies the run-to-run variation via `PYTHONHASHSEED` randomisation.

The realistic failure mode — and the only reason I don't say 20/20 — is stopping at route 3: an agent concludes "the batch order is nondeterministic because of `set()`", proposes `sorted(args.slugs)`, and ships. That *does* make the nightly output stable and makes the reported symptom vanish, while permanently freezing one member of each pair as poisoned. It's a genuinely tempting wrong fix and should catch perhaps 3–5 of 20. But those agents have still located the batch as the culprit, not the model, so they don't count as "blamed the model" either.

**To pull `caso-i` into the band**, the highest-leverage change is L2: make the corpus URLs realistic and colliding for a data reason, and move the owner-dropping into the *unshipped* ingest. Then `pages.py` keyed by url is defensible code, the `cli`/`batch` lifetime difference is a legitimate optimisation rather than a flashing arrow, and the investigator must notice the corpus collision to close the loop. Secondarily, route the solo path through `run_batch` with a single slug so the PageCache lifetime is not a one-line diff between two adjacent files.

## 6. `git status --short` — nobody committed

```
 M src/btm/harness/ingest.py
 M src/btm/harness/variants.py
?? data/scenario/
?? results/a5-hechos.json
?? results/frozen-a5.json
?? results/scenario-cribado.json
?? src/btm/harness/a5_case.py
?? src/btm/harness/a5_facts.py
?? src/btm/harness/a5_report.py
?? src/btm/harness/fix/
?? src/btm/harness/passes.py
?? src/btm/harness/scenario_corpus.py
?? src/btm/variants/A5/
?? tests/test_a5.py
?? tests/test_a5_evidence.py
?? tests/test_ingest.py
?? tests/test_passes.py
?? tests/test_scenario_corpus.py
```
HEAD is still `8608279 Fase 0: la colisión existe, y once pares la sostienen`. All A5 work is uncommitted, as expected.

## What to fix, in order

1. **L2 / difficulty (same fix).** Replace `https://github.com/{name}#{n}` with registry-style URLs where the bare name is legitimately the key, and move owner-dropping into the unshipped `ingest.py`. Fixes the realism break in both packages *and* is the only change that plausibly moves `caso-i` toward 6–11.
2. **L1.** Strip `POOR_KINDS` / `Trace.poor()` from `src/btm/system/trace.py`; they are harness-only and their presence in `code/trace.py` tells the investigator the logs were curated. `tests/test_trace.py:23-34` moves with them.
3. **Correction key.** Record explicitly that `gcol33--vectra` (pass 1) and `sile--efmt` (pass 4) are real model sampling, not the cache, and that for `yoonic--atlas` the corrupted cells are the *majority* ones. Without this the key mis-grades both a correct "half of this is the model" answer and a correct atlas diagnosis.
4. **Housekeeping.** Delete the stale `trial/` package copy; confirm the unshipped `data/taxonomy.yaml` and the withheld `justification` are deliberate.
