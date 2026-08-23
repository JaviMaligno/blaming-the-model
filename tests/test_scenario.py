import json
import re
from pathlib import Path

from btm.harness.divergence import collect
from btm.harness.scenario import build_scenario
from btm.system.taxonomy import Taxonomy
from tests.test_divergence import DocumentSensitiveModel, late_evidence_snapshot as snapshot

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"

FORBIDDEN = (
    "a1", "a2", "a3", "a4", "variant", "variante", "avería", "averia", "bug",
    "estocás", "estocas", "divergen", "escenario", "experimento", "seed",
    "held_out", "ground_truth", "ceiling_miscalibrated", "differs_from_healthy",
)


def report(tmp_path: Path, variant_id: str = "A4"):
    return collect(
        snapshot(), Taxonomy.load(TAXONOMY_PATH), DocumentSensitiveModel,
        variant_id=variant_id, run_ids=["r0", "r1"], workdir=tmp_path / "work",
    )


def test_writes_brief_runs_and_code(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out")
    assert (out / "BRIEF.md").exists()
    assert (out / "runs" / "r0.jsonl").exists()
    assert (out / "code" / "classifier.py").exists()


def test_the_package_never_names_the_experiment(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out")
    offences = []
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8").lower()
        offences += [
            (path.name, word) for word in FORBIDDEN
            if re.search(rf"\b{re.escape(word)}", body)
        ]
    assert offences == []


def test_the_first_line_of_every_run_carries_only_slug_and_run_id(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out")
    for path in (out / "runs").glob("*.jsonl"):
        first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert set(first["payload"]) == {"slug", "run_id"}


def test_runs_are_shallow_by_default(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out")
    kinds = {
        json.loads(line)["kind"]
        for line in (out / "runs" / "r0.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert kinds == {"input", "final"}


def test_rich_runs_include_the_instrumentation(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out-rich", rich=True)
    kinds = {
        json.loads(line)["kind"]
        for line in (out / "runs" / "r0.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert "model_message" in kinds and "budget" in kinds


def test_the_copied_code_is_the_variant_that_produced_the_runs(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path, "A4"), tmp_path / "out")
    assert "DEFAULT_CONFIDENCE_CEILING" in (out / "code" / "budget.py").read_text(encoding="utf-8")


def test_the_harness_is_not_shipped(tmp_path: Path) -> None:
    out = build_scenario(report(tmp_path), tmp_path / "out")
    names = {p.name for p in (out / "code").iterdir()}
    assert names.isdisjoint({"divergence.py", "scenario.py", "cli.py", "variants.py"})
