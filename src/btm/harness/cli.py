"""Línea de comandos del arnés: arma un escenario y su ground truth.

Esto es arnés: nunca se entrega. El ground truth se escribe en un directorio
hermano del paquete, no dentro.

    python -m btm.harness.cli scenario --variant A4 --repo <slug> --out out/
    python -m btm.harness.cli judgement --set B1 --out out/
"""

import argparse
from pathlib import Path

from btm.harness.divergence import collect
from btm.harness.model import AzureModel
from btm.harness.scenario import build_scenario, write_ground_truth
from btm.harness.variants import VARIANTS
from btm.system.corpus import load_snapshot
from btm.system.taxonomy import Taxonomy


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm")
    sub = parser.add_subparsers(dest="command", required=True)

    scenario = sub.add_parser("scenario")
    scenario.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    scenario.add_argument("--repo", required=True)
    scenario.add_argument("--out", type=Path, required=True)
    scenario.add_argument("--ground-truth", type=Path, default=Path("ground-truth"))
    scenario.add_argument("--runs", type=int, default=8)
    scenario.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    scenario.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    scenario.add_argument("--work", type=Path, default=Path(".work"))

    judgement = sub.add_parser("judgement")
    judgement.add_argument("--set", dest="judgement_set", required=True)
    judgement.add_argument("--out", type=Path, required=True)
    judgement.add_argument("--data", type=Path, default=Path("data/judgement"))

    args = parser.parse_args()

    if args.command == "judgement":
        from btm.harness.judgement import build_judgement_scenario, load_judgement_set

        matches = sorted(args.data.glob(f"{args.judgement_set.lower()}-*.yaml"))
        if not matches:
            raise SystemExit(f"no hay conjunto {args.judgement_set} en {args.data}")
        print(f"out={build_judgement_scenario(load_judgement_set(matches[0]), args.out)}")
        return

    report = collect(
        load_snapshot(args.repo, args.corpus),
        Taxonomy.load(args.taxonomy),
        AzureModel,
        variant_id=args.variant,
        run_ids=[f"r{i}" for i in range(args.runs)],
        workdir=args.work,
    )
    out = build_scenario(report, args.out)
    write_ground_truth(report, args.ground_truth)
    print(
        f"diverged={report.diverged_across_runs} "
        f"differs_from_healthy={report.differs_from_healthy} "
        f"ceiling_miscalibrated={report.ceiling_miscalibrated} out={out}"
    )


if __name__ == "__main__":
    main()
