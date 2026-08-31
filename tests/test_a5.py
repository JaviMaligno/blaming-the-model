"""Comportamiento de la variante A5 y de su runner de lote.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. Los snapshots
se construyen en memoria y se vuelcan a un corpus temporal, así que la suite
corre sin red y sin modelo.
"""

import importlib
import json
import re
from pathlib import Path

import pytest

from btm.harness.variants import SOURCES, VARIANTS, load_classify, materialise
from btm.system.classifier import classify as healthy_classify
from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy
from btm.variants.A5.batch import run_batch
from btm.variants.A5.cli import run_one
from btm.variants.A5.pages import PageCache

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"
SHARED_URL = "https://x.invalid/readme"

ACME_TEXT = "acme pay cobros con tarjeta para comercios"
BETA_TEXT = "beta mesh enrutado entre servicios en kubernetes"


class FakeModel:
    """Devuelve una respuesta fija y guarda los prompts que ha recibido."""

    def __init__(self, code: str = "business.payments") -> None:
        self.code = code
        self.prompts: list[str] = []

    def complete(self, messages: list[dict]) -> str:
        self.prompts.append(messages[0]["content"])
        return f'{{"code": "{self.code}", "confidence": 0.9, "justification": "-"}}'


def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


def acme(readme_url: str = SHARED_URL) -> RepoSnapshot:
    return RepoSnapshot(
        slug="acme-pay",
        name="acme pay",
        description="cobros para comercios",
        documents=[
            Document(url=readme_url, title="readme", text=ACME_TEXT, kind="docs"),
            Document(
                url="https://x.invalid/acme-install",
                title="install",
                text="acme pay instalacion uso",
                kind="docs",
            ),
        ],
    )


def beta(readme_url: str = SHARED_URL) -> RepoSnapshot:
    return RepoSnapshot(
        slug="beta-mesh",
        name="beta mesh",
        description="malla de servicios",
        documents=[
            Document(url=readme_url, title="readme", text=BETA_TEXT, kind="docs"),
            Document(
                url="https://x.invalid/beta-install",
                title="install",
                text="beta mesh instalacion uso",
                kind="docs",
            ),
        ],
    )


def write_corpus(root: Path, snapshots: list[RepoSnapshot]) -> Path:
    for snapshot in snapshots:
        target = root / snapshot.slug
        target.mkdir(parents=True, exist_ok=True)
        (target / "snapshot.json").write_text(
            snapshot.model_dump_json(indent=2), encoding="utf-8"
        )
    return root


def colliding_corpus(tmp_path: Path) -> Path:
    return write_corpus(tmp_path / "corpus", [acme(), beta()])


def disjoint_corpus(tmp_path: Path) -> Path:
    return write_corpus(
        tmp_path / "corpus",
        [acme("https://x.invalid/acme-readme"), beta("https://x.invalid/beta-readme")],
    )


# --- la caché -----------------------------------------------------------


def test_the_second_read_of_a_url_comes_from_the_memo() -> None:
    cache = PageCache()
    assert cache.get_or_load(SHARED_URL, acme()) == ACME_TEXT
    # Un snapshot que ya no contiene la url: si respondiera, es que la memorizó.
    empty = RepoSnapshot(slug="empty", name="empty", documents=[])
    assert cache.get_or_load(SHARED_URL, empty) == ACME_TEXT


def test_an_unknown_url_raises_key_error() -> None:
    with pytest.raises(KeyError):
        PageCache().get_or_load("https://x.invalid/missing", acme())


def test_two_snapshots_sharing_a_url_get_the_text_of_the_first_one() -> None:
    cache = PageCache()
    first = cache.get_or_load(SHARED_URL, acme())
    second = cache.get_or_load(SHARED_URL, beta())
    assert first == second == ACME_TEXT


def test_the_first_one_to_ask_is_the_one_that_decides() -> None:
    cache = PageCache()
    assert cache.get_or_load(SHARED_URL, beta()) == BETA_TEXT
    assert cache.get_or_load(SHARED_URL, acme()) == BETA_TEXT


# --- el lote ------------------------------------------------------------


def test_the_batch_serves_a_different_context_depending_on_the_order(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    first = FakeModel()
    run_batch(["acme-pay", "beta-mesh"], root, taxonomy(), first)
    second = FakeModel()
    run_batch(["beta-mesh", "acme-pay"], root, taxonomy(), second)

    beta_when_second = first.prompts[1]
    beta_when_first = second.prompts[0]
    assert beta_when_second != beta_when_first
    assert ACME_TEXT in beta_when_second and BETA_TEXT not in beta_when_second
    assert BETA_TEXT in beta_when_first and ACME_TEXT not in beta_when_first


def test_the_batch_reuses_one_cache_across_repositories(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    model = FakeModel()
    rows = run_batch(["acme-pay", "beta-mesh"], root, taxonomy(), model)
    assert [row.slug for row in rows] == ["acme-pay", "beta-mesh"]
    assert ACME_TEXT in model.prompts[1]


def test_the_entry_point_processes_each_repository_once(tmp_path: Path, capsys) -> None:
    from btm.variants.A5.batch import main

    root = colliding_corpus(tmp_path)
    main(
        FakeModel(),
        ["acme-pay", "beta-mesh", "acme-pay", "--corpus", str(root),
         "--taxonomy", str(TAXONOMY_PATH)],
    )
    printed = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert sorted(row["slug"] for row in printed) == ["acme-pay", "beta-mesh"]


# --- la corrida suelta --------------------------------------------------


def test_a_single_run_never_serves_someone_elses_page(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    for slug, own, other in (
        ("beta-mesh", BETA_TEXT, ACME_TEXT),
        ("acme-pay", ACME_TEXT, BETA_TEXT),
    ):
        model = FakeModel()
        run_one(slug, root, taxonomy(), model)
        assert own in model.prompts[0]
        assert other not in model.prompts[0]


def test_repeated_single_runs_are_identical(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    prompts = []
    for _ in range(3):
        model = FakeModel()
        run_one("beta-mesh", root, taxonomy(), model)
        prompts.append(model.prompts[0])
    assert len(set(prompts)) == 1


# --- paridad con el sistema sano ---------------------------------------


def test_the_toolbox_without_a_cache_reads_from_its_own_snapshot() -> None:
    from btm.system.tools import ToolBox as HealthyToolBox
    from btm.variants.A5.tools import ToolBox

    plain = ToolBox(beta(), taxonomy(), run_id="r0")
    healthy = HealthyToolBox(beta(), taxonomy(), run_id="r0")
    assert plain.fetch_page(SHARED_URL) == healthy.fetch_page(SHARED_URL) == BETA_TEXT
    with pytest.raises(KeyError):
        plain.fetch_page("https://x.invalid/missing")


def test_classify_without_a_cache_matches_the_healthy_classifier() -> None:
    from btm.variants.A5.classifier import classify

    plain = FakeModel()
    healthy = FakeModel()
    result, _ = classify(beta(), taxonomy(), plain, run_id="r0")
    expected, _ = healthy_classify(beta(), taxonomy(), healthy, run_id="r0")
    assert plain.prompts == healthy.prompts
    # Cada árbol define su propia `Classification`, así que se comparan valores.
    assert result.model_dump() == expected.model_dump()


def test_without_collisions_the_batch_matches_the_healthy_system(tmp_path: Path) -> None:
    root = disjoint_corpus(tmp_path)
    snapshots = [acme("https://x.invalid/acme-readme"), beta("https://x.invalid/beta-readme")]

    healthy = FakeModel()
    healthy_codes = [
        healthy_classify(s, taxonomy(), healthy, run_id=s.slug)[0].code for s in snapshots
    ]

    batched = FakeModel()
    rows = run_batch([s.slug for s in snapshots], root, taxonomy(), batched)

    assert batched.prompts == healthy.prompts
    assert [row.code for row in rows] == healthy_codes


# --- materialización ----------------------------------------------------


def test_a5_is_registered_with_its_five_modules() -> None:
    assert set(VARIANTS["A5"]) == {"pages.py", "tools.py", "classifier.py", "batch.py", "cli.py"}
    assert set(SOURCES["A5"]) == set(VARIANTS["A5"])


def test_the_materialised_tree_has_no_absolute_system_imports(tmp_path: Path) -> None:
    package = materialise("A5", tmp_path)
    assert {"pages.py", "batch.py", "cli.py"} <= {p.name for p in package.glob("*.py")}
    for path in package.glob("*.py"):
        assert "btm.system" not in path.read_text(encoding="utf-8"), path.name


def test_the_materialised_tree_runs_a_batch(tmp_path: Path) -> None:
    load_classify("A5", tmp_path / "tree")
    module = importlib.import_module("btm_system_A5.batch")
    loaded_taxonomy = importlib.import_module("btm_system_A5.taxonomy").Taxonomy
    root = colliding_corpus(tmp_path)

    model = FakeModel()
    rows = module.run_batch(
        ["acme-pay", "beta-mesh"], root, loaded_taxonomy.load(TAXONOMY_PATH), model
    )
    assert [row.slug for row in rows] == ["acme-pay", "beta-mesh"]
    assert ACME_TEXT in model.prompts[1]


# --- vocabulario --------------------------------------------------------


FORBIDDEN = (
    "avería", "averia", "bug", "escenario", "experimento", "variante",
    "estocástico", "estocastico", "envenenad", "arnés", "arnes",
)


def test_no_a5_file_names_the_work_it_belongs_to() -> None:
    root = Path(__file__).parents[1] / "src" / "btm" / "variants" / "A5"
    for path in sorted(root.glob("*.py")):
        body = path.read_text(encoding="utf-8").lower()
        for word in FORBIDDEN:
            assert word not in body, (path.name, word)
        assert not re.search(r"\ba[1-5]\b", body), path.name
