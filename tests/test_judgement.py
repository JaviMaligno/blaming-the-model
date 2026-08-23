from pathlib import Path

from btm.harness.judgement import build_judgement_scenario, load_judgement_set

DATA = Path(__file__).parents[1] / "data" / "judgement"


def test_loads_visible_and_held_out_cases() -> None:
    judgement_set = load_judgement_set(DATA / "b1-agency.yaml")
    assert judgement_set.set_id == "B1"
    assert len(judgement_set.visible) == 3
    assert len(judgement_set.held_out) == 3


def test_every_set_has_held_out_cases() -> None:
    for path in sorted(DATA.glob("*.yaml")):
        assert load_judgement_set(path).held_out, f"{path.name} no tiene held-out"


def test_held_out_defeats_the_obvious_keyword_rule() -> None:
    judgement_set = load_judgement_set(DATA / "b1-agency.yaml")
    keywords = ("cliente", "bindings", "wrapper")
    wrong = [
        case for case in judgement_set.held_out
        if any(k in case.text.lower() for k in keywords) != (case.label == "third_party")
    ]
    assert wrong, "el held-out debe romper el atajo, o no mide nada"


def test_scenario_hides_the_held_out_cases(tmp_path: Path) -> None:
    judgement_set = load_judgement_set(DATA / "b1-agency.yaml")
    brief = (build_judgement_scenario(judgement_set, tmp_path) / "BRIEF.md").read_text(
        encoding="utf-8"
    )
    for case in judgement_set.held_out:
        assert case.text not in brief
    for case in judgement_set.visible:
        assert case.text in brief


def test_scenario_hides_the_labels_and_the_notes(tmp_path: Path) -> None:
    judgement_set = load_judgement_set(DATA / "b1-agency.yaml")
    brief = (build_judgement_scenario(judgement_set, tmp_path) / "BRIEF.md").read_text(
        encoding="utf-8"
    )
    for case in judgement_set.visible:
        assert case.note not in brief
        assert case.label not in brief
