"""Corridas de una variante, línea base sana y las señales que las separan.

Esto es arnés: nunca se entrega. Las cuatro averías no se manifiestan igual, y
por eso el informe lleva tres señales en lugar de una:

- `diverged_across_runs`: la misma entrada da códigos distintos según la
  corrida. Sólo A1 (y A3, que la arrastra) se ve así.
- `differs_from_healthy`: mismo repositorio y mismo `run_id`, sano contra
  averiado. Es una comparación determinista, no depende del muestreo del
  modelo, y es la que delata a A2 y a A4.
- `ceiling_miscalibrated`: el techo de confianza declarado no coincide con el
  que declara la línea base para la misma corrida.

Por eso el informe guarda también `healthy_runs`: sin la línea base, dos de
las cuatro averías no tienen señal observable.
"""

import json
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from btm.harness.variants import load_classify
from btm.system.classifier import Classification
from btm.system.classifier import classify as classify_healthy
from btm.system.corpus import RepoSnapshot
from btm.system.taxonomy import Taxonomy


class Run(BaseModel):
    """Una corrida: su identificador, lo que respondió y lo que hizo."""

    run_id: str
    classification: Classification
    trace_jsonl: str


class SignalReport(BaseModel):
    """Las corridas de una variante, su línea base sana y las tres señales."""

    slug: str
    variant_id: str
    runs: list[Run]
    healthy_runs: list[Run]
    diverged_across_runs: bool
    differs_from_healthy: bool
    ceiling_miscalibrated: bool


def _as_classification(result: object) -> Classification:
    """Reconstruye la clasificación con el tipo del árbol sano.

    El árbol materializado de una variante define sus propias clases, así que
    lo que devuelve no es la `Classification` de `btm.system` aunque tenga los
    mismos campos.
    """
    return Classification(
        code=result.code,
        confidence=result.confidence,
        justification=result.justification,
    )


def _ceiling(run: Run) -> float:
    for line in run.trace_jsonl.strip().splitlines():
        event = json.loads(line)
        if event["kind"] == "budget":
            return event["payload"]["declared_ceiling"]
    return 1.0


def _observable(run: Run) -> tuple:
    """La respuesta que produce una corrida: lo que el sistema publica.

    Deliberadamente NO incluye la traza. Cualquier avería cambia algún evento
    interno, así que compararla haría que `differs_from_healthy` fuese cierta
    siempre y la señal no distinguiría nada. Lo que tiene que diferir es la
    salida.
    """
    return (
        run.classification.code,
        run.classification.confidence,
        run.classification.justification,
    )


def collect(
    snapshot: RepoSnapshot,
    taxonomy: Taxonomy,
    model_factory: Callable[[], object],
    *,
    variant_id: str,
    run_ids: list[str],
    workdir: Path,
) -> SignalReport:
    """Corre la variante y la línea base sobre el mismo repositorio y los
    mismos `run_id`, y devuelve las corridas con sus señales."""
    classify_variant = load_classify(variant_id, workdir)

    def runs_with(fn: Callable) -> list[Run]:
        collected: list[Run] = []
        for run_id in run_ids:
            classification, trace = fn(snapshot, taxonomy, model_factory(), run_id=run_id)
            collected.append(
                Run(
                    run_id=run_id,
                    classification=_as_classification(classification),
                    trace_jsonl=trace.to_jsonl(),
                )
            )
        return collected

    runs = runs_with(classify_variant)
    healthy = runs_with(classify_healthy)

    codes = {run.classification.code for run in runs}
    differs = any(_observable(a) != _observable(b) for a, b in zip(runs, healthy))
    miscalibrated = any(_ceiling(a) != _ceiling(b) for a, b in zip(runs, healthy))

    return SignalReport(
        slug=snapshot.slug,
        variant_id=variant_id,
        runs=runs,
        healthy_runs=healthy,
        diverged_across_runs=len(codes) > 1,
        differs_from_healthy=differs,
        ceiling_miscalibrated=miscalibrated,
    )
