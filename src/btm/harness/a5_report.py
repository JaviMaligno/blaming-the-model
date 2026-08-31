"""Reúne las pasadas, escribe el ground truth, evalúa los cuatro hechos y monta
los dos paquetes.

Esto es arnés: nunca se entrega. No lanza inferencia; consume lo que dejaron
`btm.harness.passes` (las pasadas compartida y reparada, las de determinismo con
cliente de mentira, las corridas sueltas) y el fichero de certificación por
contexto, y produce cuatro salidas:

- `ground-truth/a5.json`: qué recibió cada corrida de cada pasada.
- `results/a5-hechos.json`: los cuatro hechos con sus números.
- los dos paquetes, sin código y con código.
- `results/frozen-a5.json`: el digest de cada paquete, fichero a fichero.
"""

import argparse
import json
from pathlib import Path

from btm.harness.a5_case import audit_package, build_case, freeze
from btm.harness.a5_facts import (
    StabilityFact,
    TailFact,
    determinism_fact,
    directions,
    fix_fact,
    ground_truth,
    load_passes,
    load_solo,
    prompt_bytes_fact,
)


def _five(root: Path, name: str) -> list[Path]:
    return [root / name / f"p{i}.json" for i in range(1, 6)]


def _tail_block(tail: TailFact) -> dict:
    """La cola, tal y como se escribe en el ground truth y en los hechos."""
    return {
        "entries": [
            entry.model_dump()
            | {"resampled_stable": entry.resampled_stable, "ok": entry.ok}
            for entry in tail.entries
        ],
        "events": sum(len(entry.events) for entry in tail.entries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-a5-report")
    parser.add_argument("--runs", type=Path, required=True, help="raíz de las pasadas crudas")
    parser.add_argument("--cases", type=Path, required=True, help="dónde montar los paquetes")
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--ground-truth", type=Path, default=Path("ground-truth/a5.json"))
    parser.add_argument("--facts", type=Path, default=Path("results/a5-hechos.json"))
    parser.add_argument("--frozen", type=Path, default=Path("results/frozen-a5.json"))
    parser.add_argument("--deployment", default="gpt-5-mini")
    args = parser.parse_args()

    shared = load_passes(_five(args.runs, "real"))
    keyed = load_passes(_five(args.runs, "keyed"))
    solo = load_solo(args.runs / "real" / "solo.json")
    twin_a = load_passes([args.runs / "det" / f"p{i}-a.json" for i in range(1, 6)])
    twin_b = load_passes([args.runs / "det" / f"p{i}-b.json" for i in range(1, 6)])
    stability = StabilityFact.model_validate_json(
        (args.runs / "real" / "stability.json").read_text(encoding="utf-8")
    )
    tail = TailFact.model_validate_json(
        (args.runs / "real" / "tail.json").read_text(encoding="utf-8")
    )
    tail_keyed = TailFact.model_validate_json(
        (args.runs / "real" / "tail-keyed.json").read_text(encoding="utf-8")
    )

    # Las pasadas se renombran para el paquete: nada de p1..p5, que suena a
    # identificador interno, y nada que sugiera un orden de siembra.
    for n, result in enumerate(shared, 1):
        result.pass_id = f"pasada-{n}"

    truth = ground_truth(shared, solo, deployment=args.deployment, corpus=args.corpus)
    # La lista blanca: qué corridas cambiaron de etiqueta sin que nadie les
    # sirviera una página de otro proyecto. Para ésas la respuesta correcta es
    # el muestreo, y quien lo diga acierta.
    truth["sampling_tail"] = _tail_block(tail)
    # La tabla por dirección: qué etiqueta da cada contexto congelado, veinte
    # veces por lado. Es lo que impide leer al revés las direcciones donde la
    # celda mayoritaria de la tabla es la corrupta.
    truth["by_direction"] = [
        e.model_dump() | {"labels_differ": e.labels_differ, "stable": e.stable}
        for e in stability.projects
    ]
    args.ground_truth.parent.mkdir(parents=True, exist_ok=True)
    args.ground_truth.write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    bytes_fact = prompt_bytes_fact(shared)
    determinism = determinism_fact(twin_a, twin_b)
    repair = fix_fact(keyed, solo)

    facts = {
        "prompt_bytes": {
            "ok": bytes_fact.ok,
            "cases": [c.model_dump() | {"delta": c.delta} for c in bytes_fact.cases],
        },
        "determinism": determinism.model_dump() | {"ok": determinism.ok},
        "stability_by_context": {
            "ok": stability.ok,
            "threshold": stability.threshold,
            "model_calls": stability.model_calls,
            "projects": [
                e.model_dump()
                | {"labels_differ": e.labels_differ, "stable": e.stable, "ok": e.ok}
                for e in stability.projects
            ],
        },
        "repair": repair.model_dump() | {
            "ok": repair.ok,
            "sampling_resample": _tail_block(tail_keyed),
        },
        "sampling_tail": {"ok": tail.ok, "model_calls": tail.model_calls,
                          "threshold": tail.threshold, **_tail_block(tail)},
    }
    facts["directions"] = {"ok": True, "rows": directions(shared, solo)}
    facts["changes_per_pass"] = {
        "ok": all(2 <= len(p["changed"]) <= 4 for p in truth["passes"]),
        "per_pass": {p["pass_id"]: p["changed"] for p in truth["passes"]},
        "unexplained": {
            p["pass_id"]: [s for s in p["changed"] if s not in p["contaminated"]]
            for p in truth["passes"]
        },
    }
    args.facts.parent.mkdir(parents=True, exist_ok=True)
    args.facts.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    cases = {
        "caso-j": build_case(shared, args.corpus, args.cases / "caso-j", with_code=False),
        "caso-k": build_case(shared, args.corpus, args.cases / "caso-k", with_code=True),
    }
    offences = {name: audit_package(path) for name, path in cases.items()}
    if any(offences.values()):
        raise SystemExit(f"vocabulario: {offences}")

    args.frozen.write_text(
        json.dumps(freeze(cases), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for name, fact in facts.items():
        print(f"{name:22} {'OK' if fact['ok'] else 'NO PASA'}")
    for name, path in cases.items():
        print(f"{name}: {len([p for p in path.rglob('*') if p.is_file()])} ficheros en {path}")


if __name__ == "__main__":
    main()
