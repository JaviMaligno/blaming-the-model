from pathlib import Path

from btm.harness.variants import VARIANTS, load_classify, materialise

SYSTEM = Path(__file__).parents[1] / "src" / "btm" / "system"


def healthy_text(name: str) -> str:
    """El módulo sano, con los imports reescritos como los reescribe materialise."""
    return (SYSTEM / name).read_text(encoding="utf-8").replace("from btm.system.", "from .")


def test_a3_also_carries_the_retrieval_variant() -> None:
    assert set(VARIANTS["A3"]) == {"classifier.py", "tools.py"}


def test_materialise_writes_a_complete_system_tree(tmp_path: Path) -> None:
    package = materialise("A4", tmp_path)
    expected = {p.name for p in SYSTEM.glob("*.py")}
    assert {p.name for p in package.glob("*.py")} == expected


def test_the_variant_module_replaces_the_healthy_one(tmp_path: Path) -> None:
    package = materialise("A4", tmp_path)
    assert "DEFAULT_CONFIDENCE_CEILING" in (package / "budget.py").read_text(encoding="utf-8")
    assert "DEFAULT_CONFIDENCE_CEILING" not in (SYSTEM / "budget.py").read_text(encoding="utf-8")


def test_untouched_modules_are_identical_to_the_healthy_ones(tmp_path: Path) -> None:
    package = materialise("A4", tmp_path)
    for name in ("taxonomy.py", "corpus.py", "tools.py"):
        assert (package / name).read_text(encoding="utf-8") == healthy_text(name)


def test_the_materialised_tree_imports_relatively(tmp_path: Path) -> None:
    package = materialise("A3", tmp_path)
    for path in package.glob("*.py"):
        assert "btm.system" not in path.read_text(encoding="utf-8"), path.name
    assert "from .budget import" in (package / "classifier.py").read_text(encoding="utf-8")


def test_load_classify_returns_a_working_entry_point(tmp_path: Path) -> None:
    classify = load_classify("A2", tmp_path)
    assert callable(classify)


def test_no_variant_file_names_the_experiment() -> None:
    root = Path(__file__).parents[1] / "src" / "btm" / "variants"
    for path in root.rglob("*.py"):
        body = path.read_text(encoding="utf-8").lower()
        for word in ("avería", "averia", "bug", "escenario", "experimento", "variante"):
            assert word not in body, (path, word)
