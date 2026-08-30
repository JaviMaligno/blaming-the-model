"""Aptitud estructural de un repositorio para cada avería.

Una avería sólo puede cambiar la respuesta si cambia lo que el modelo llega a
leer, o el prompt con el que lo lee. Eso se comprueba sin invocar a ningún
modelo: basta ejecutar el clasificador y mirar la traza.

El filtro es barato y descarta antes de gastar inferencia. Que un repositorio
sea apto no garantiza que la señal aparezca con el modelo real —eso lo decide
el gate de calibración—, pero que no lo sea sí garantiza que no aparecerá.
"""

import json
import tempfile
from pathlib import Path

from pydantic import BaseModel

from btm.harness.variants import load_classify
from btm.system.classifier import classify as classify_healthy
from btm.system.corpus import RepoSnapshot
from btm.system.taxonomy import Taxonomy

RUN_IDS = tuple(f"r{i}" for i in range(8))


class _Mute:
    """Responde siempre lo mismo: aquí sólo importa la traza, no la respuesta."""

    def complete(self, messages: list[dict]) -> str:
        return '{"code": "devtools.libraries", "confidence": 0.9, "justification": "-"}'


class Fitness(BaseModel):
    slug: str
    has_description: bool
    documents: int
    context_varies_across_runs: bool
    context_differs_from_healthy: dict[str, bool]
    ceiling_differs: bool
    fit_for: list[str]


def _trace_facts(trace) -> tuple[tuple[str, ...], float, int]:
    urls: tuple[str, ...] = ()
    ceiling = 1.0
    answered = 0
    for event in trace.events:
        if event.kind == "context_documents":
            urls = tuple(event.payload["urls"])
        elif event.kind == "budget":
            ceiling = event.payload["declared_ceiling"]
            answered = event.payload["answered"]
    return urls, ceiling, answered


def assess(snapshot: RepoSnapshot, taxonomy: Taxonomy) -> Fitness:
    healthy: dict[str, tuple] = {}
    for run_id in RUN_IDS:
        _, trace = classify_healthy(snapshot, taxonomy, _Mute(), run_id=run_id)
        healthy[run_id] = _trace_facts(trace)

    differs: dict[str, bool] = {}
    ceiling_differs = False
    with tempfile.TemporaryDirectory() as tmp:
        for variant_id in ("A1", "A2", "A3", "A4"):
            classify_variant = load_classify(variant_id, Path(tmp) / variant_id)
            changed = False
            for run_id in RUN_IDS:
                _, trace = classify_variant(snapshot, taxonomy, _Mute(), run_id=run_id)
                urls, ceiling, _ = _trace_facts(trace)
                if urls != healthy[run_id][0]:
                    changed = True
                if variant_id == "A4" and ceiling != healthy[run_id][1]:
                    ceiling_differs = True
            differs[variant_id] = changed

    varies = len({facts[0] for facts in healthy.values()}) > 1

    fit: list[str] = []
    # A1 y A3 necesitan que barajar el orden cambie qué documentos entran.
    if differs["A1"]:
        fit.append("A1")
    if differs["A3"]:
        fit.append("A3")
    # A2 sólo tiene sentido donde falta la descripción y su consulta aporta.
    if snapshot.description is None and differs["A2"]:
        fit.append("A2")
    # A4 necesita que quedarse sin presupuesto recorte la evidencia.
    if differs["A4"] or ceiling_differs:
        fit.append("A4")

    return Fitness(
        slug=snapshot.slug,
        has_description=snapshot.description is not None,
        documents=len(snapshot.documents),
        context_varies_across_runs=varies,
        context_differs_from_healthy=differs,
        ceiling_differs=ceiling_differs,
        fit_for=fit,
    )


def report(root: Path, taxonomy_path: Path) -> list[Fitness]:
    from btm.system.corpus import load_all

    taxonomy = Taxonomy.load(taxonomy_path)
    return [assess(snapshot, taxonomy) for snapshot in load_all(root)]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="btm-fitness")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = report(args.corpus, args.taxonomy)
    if args.json:
        print(json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2))
        return

    print(f"{'repositorio':44} {'docs':>4} {'desc':>5}  apto para")
    for result in results:
        desc = "sí" if result.has_description else "no"
        fit = ", ".join(result.fit_for) or "—"
        print(f"{result.slug[:44]:44} {result.documents:>4} {desc:>5}  {fit}")
    covered = {v for r in results for v in r.fit_for}
    missing = sorted({"A1", "A2", "A3", "A4"} - covered)
    print(f"\n{len(results)} repositorios. Sin cobertura: {', '.join(missing) or 'ninguna'}")


if __name__ == "__main__":
    main()
