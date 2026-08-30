"""Gate de calibración: ¿produce cada avería su señal sobre repositorios reales?

El gate no es el mismo para todas. A1 y A3 tienen que divergir entre corridas;
A2 y A4 se observan contra la línea base sana, que es una comparación
determinista y no depende del muestreo del modelo. Un par avería-repositorio
que no produce su señal se descarta: se prueba otro repositorio, nunca se
retoca la avería para forzarla.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from btm.harness.divergence import collect
from btm.harness.fitness import assess
from btm.harness.model import AzureModel
from btm.system.corpus import load_all
from btm.system.taxonomy import Taxonomy

# Qué señal tiene que enseñar cada avería para pasar el gate.
REQUIRED = {
    "A1": ("diverged_across_runs",),
    "A2": ("differs_from_healthy",),
    "A3": ("diverged_across_runs", "differs_from_healthy"),
    "A4": ("differs_from_healthy", "ceiling_miscalibrated"),
}


def _passes(report, variant_id: str) -> bool:
    return all(getattr(report, field) for field in REQUIRED[variant_id])


def run_one(snapshot, taxonomy, variant_id, deployment, runs, workdir):
    report = collect(
        snapshot,
        taxonomy,
        lambda: AzureModel(deployment=deployment),
        variant_id=variant_id,
        run_ids=[f"r{i}" for i in range(runs)],
        workdir=workdir / f"{snapshot.slug}-{variant_id}",
    )
    return {
        "slug": snapshot.slug,
        "variant": variant_id,
        "diverged": report.diverged_across_runs,
        "differs": report.differs_from_healthy,
        "ceiling": report.ceiling_miscalibrated,
        "passes": _passes(report, variant_id),
        "codes": sorted({r.classification.code for r in report.runs}),
        "healthy_codes": sorted({r.classification.code for r in report.healthy_runs}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-gate")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--work", type=Path, default=Path(".work/gate"))
    parser.add_argument("--out", type=Path, default=Path("results/gate.json"))
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--per-variant", type=int, default=3)
    parser.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    taxonomy = Taxonomy.load(args.taxonomy)
    snapshots = load_all(args.corpus)
    by_slug = {s.slug: s for s in snapshots}

    # Sólo se prueban pares que el evaluador de aptitud ya da por posibles:
    # gastar inferencia en uno que no puede producir señal no informa de nada.
    fitness = {f.slug: f for f in (assess(s, taxonomy) for s in snapshots)}
    jobs: list[tuple[str, str]] = []
    for variant_id in ("A1", "A2", "A3", "A4"):
        candidates = [
            slug for slug, f in fitness.items()
            if variant_id in f.fit_for
            and (variant_id != "A4" or f.context_differs_from_healthy["A4"])
        ]
        candidates.sort(key=lambda s: -len(by_slug[s].documents))
        for slug in candidates[: args.per_variant]:
            jobs.append((slug, variant_id))

    print(f"{len(jobs)} pares avería-repositorio, {args.runs} corridas cada uno "
          f"(más su línea base), con {args.deployment}")

    args.work.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda job: run_one(
                    by_slug[job[0]], taxonomy, job[1], args.deployment, args.runs, args.work
                ),
                jobs,
            )
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'repositorio':46} {'av.':>4} {'div':>4} {'dif':>4} {'techo':>6} {'gate':>6}")
    for r in sorted(results, key=lambda r: (r["variant"], r["slug"])):
        mark = "PASA" if r["passes"] else "no"
        print(f"{r['slug'][:46]:46} {r['variant']:>4} {str(r['diverged']):>5} "
              f"{str(r['differs']):>5} {str(r['ceiling']):>6} {mark:>6}")
    for variant_id in ("A1", "A2", "A3", "A4"):
        rows = [r for r in results if r["variant"] == variant_id]
        print(f"{variant_id}: {sum(r['passes'] for r in rows)}/{len(rows)} repositorios pasan")
    print(f"\nDetalle en {args.out}")


if __name__ == "__main__":
    main()
