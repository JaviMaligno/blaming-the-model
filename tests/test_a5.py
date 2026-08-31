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

# Dos proyectos homónimos —mismo nombre de repositorio, distinto dueño— y un
# tercero con nombre propio. Las urls son las del corpus: el fragmento numera
# la sección dentro del documento.
ACME_TEXT = "pay cobros con tarjeta para comercios de barrio"
GLOBEX_TEXT = "pay malla de servicios y enrutado dentro de kubernetes"
MESH_TEXT = "mesh malla de servicios y enrutado dentro de kubernetes"

ACME_README = "https://github.com/acme/pay#0"
GLOBEX_README = "https://github.com/globex/pay#0"
MESH_README = "https://github.com/globex/mesh#0"


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


def repository(owner: str, repo: str, description: str, summary: str) -> RepoSnapshot:
    """Un snapshot con dos secciones, como los del corpus."""
    base = f"https://github.com/{owner}/{repo}"
    return RepoSnapshot(
        slug=f"{owner}--{repo}",
        name=repo,
        description=description,
        documents=[
            Document(url=f"{base}#0", title="readme", text=summary, kind="readme"),
            Document(
                url=f"{base}#1",
                title="install",
                text=f"{repo} instalacion uso {owner}",
                kind="readme",
            ),
        ],
    )


def acme() -> RepoSnapshot:
    return repository("acme", "pay", "cobros para comercios", ACME_TEXT)


def globex() -> RepoSnapshot:
    return repository("globex", "pay", "malla de servicios", GLOBEX_TEXT)


def mesh() -> RepoSnapshot:
    return repository("globex", "mesh", "malla de servicios", MESH_TEXT)


def write_corpus(root: Path, snapshots: list[RepoSnapshot]) -> Path:
    for snapshot in snapshots:
        target = root / snapshot.slug
        target.mkdir(parents=True, exist_ok=True)
        (target / "snapshot.json").write_text(
            snapshot.model_dump_json(indent=2), encoding="utf-8"
        )
    return root


def colliding_corpus(tmp_path: Path) -> Path:
    return write_corpus(tmp_path / "corpus", [acme(), globex()])


def disjoint_corpus(tmp_path: Path) -> Path:
    return write_corpus(tmp_path / "corpus", [acme(), mesh()])


# --- la caché -----------------------------------------------------------


def test_the_second_read_of_a_section_comes_from_the_memo() -> None:
    cache = PageCache()
    assert cache.get_or_load(ACME_README, acme()) == ACME_TEXT
    # El mismo proyecto sin documentos que leer: si responde, es que lo memorizó.
    hollow = RepoSnapshot(slug="acme--pay", name="pay", documents=[])
    assert cache.get_or_load(ACME_README, hollow) == ACME_TEXT


def test_an_unknown_url_raises_key_error() -> None:
    with pytest.raises(KeyError):
        PageCache().get_or_load("https://github.com/acme/pay#9", acme())


def test_two_homonymous_projects_get_the_text_of_the_first_one() -> None:
    cache = PageCache()
    first = cache.get_or_load(ACME_README, acme())
    second = cache.get_or_load(GLOBEX_README, globex())
    assert first == second == ACME_TEXT


def test_the_first_homonym_to_ask_is_the_one_that_decides() -> None:
    cache = PageCache()
    assert cache.get_or_load(GLOBEX_README, globex()) == GLOBEX_TEXT
    assert cache.get_or_load(ACME_README, acme()) == GLOBEX_TEXT


def test_projects_with_different_names_never_share_a_section() -> None:
    cache = PageCache()
    assert cache.get_or_load(ACME_README, acme()) == ACME_TEXT
    assert cache.get_or_load(MESH_README, mesh()) == MESH_TEXT
    # Y en el orden contrario tampoco, con la caché ya poblada.
    assert cache.get_or_load(MESH_README, mesh()) == MESH_TEXT
    assert cache.get_or_load(ACME_README, acme()) == ACME_TEXT


def test_every_section_of_a_project_is_memoised_apart() -> None:
    cache = PageCache()
    assert cache.get_or_load(ACME_README, acme()) == ACME_TEXT
    assert cache.get_or_load("https://github.com/acme/pay#1", acme()).endswith("acme")
    assert len(cache) == 2


# --- el lote ------------------------------------------------------------


def test_the_batch_serves_a_different_context_depending_on_the_order(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    first = FakeModel()
    run_batch(["acme--pay", "globex--pay"], root, taxonomy(), first)
    second = FakeModel()
    run_batch(["globex--pay", "acme--pay"], root, taxonomy(), second)

    globex_when_second = first.prompts[1]
    globex_when_first = second.prompts[0]
    assert globex_when_second != globex_when_first
    assert ACME_TEXT in globex_when_second and GLOBEX_TEXT not in globex_when_second
    assert GLOBEX_TEXT in globex_when_first and ACME_TEXT not in globex_when_first


def test_the_batch_reuses_one_cache_across_repositories(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    model = FakeModel()
    rows = run_batch(["acme--pay", "globex--pay"], root, taxonomy(), model)
    assert [row.slug for row in rows] == ["acme--pay", "globex--pay"]
    assert ACME_TEXT in model.prompts[1]


def test_a_batch_of_differently_named_projects_keeps_each_context_its_own(
    tmp_path: Path,
) -> None:
    root = disjoint_corpus(tmp_path)
    for order, texts in (
        (["acme--pay", "globex--mesh"], [ACME_TEXT, MESH_TEXT]),
        (["globex--mesh", "acme--pay"], [MESH_TEXT, ACME_TEXT]),
    ):
        model = FakeModel()
        run_batch(order, root, taxonomy(), model)
        for prompt, own in zip(model.prompts, texts):
            assert own in prompt
        assert MESH_TEXT not in model.prompts[order.index("acme--pay")]
        assert ACME_TEXT not in model.prompts[order.index("globex--mesh")]


def test_the_entry_point_processes_each_repository_once(tmp_path: Path, capsys) -> None:
    from btm.variants.A5.batch import main

    root = colliding_corpus(tmp_path)
    main(
        FakeModel(),
        ["acme--pay", "globex--pay", "acme--pay", "--corpus", str(root),
         "--taxonomy", str(TAXONOMY_PATH)],
    )
    printed = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert sorted(row["slug"] for row in printed) == ["acme--pay", "globex--pay"]


# --- la corrida suelta --------------------------------------------------


def test_a_single_run_never_serves_someone_elses_page(tmp_path: Path) -> None:
    root = colliding_corpus(tmp_path)
    for slug, own, other in (
        ("globex--pay", GLOBEX_TEXT, ACME_TEXT),
        ("acme--pay", ACME_TEXT, GLOBEX_TEXT),
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
        run_one("globex--pay", root, taxonomy(), model)
        prompts.append(model.prompts[0])
    assert len(set(prompts)) == 1


# --- paridad con el sistema sano ---------------------------------------


def test_the_toolbox_without_a_cache_reads_from_its_own_snapshot() -> None:
    from btm.system.tools import ToolBox as HealthyToolBox
    from btm.variants.A5.tools import ToolBox

    plain = ToolBox(globex(), taxonomy(), run_id="r0")
    healthy = HealthyToolBox(globex(), taxonomy(), run_id="r0")
    assert plain.fetch_page(GLOBEX_README) == healthy.fetch_page(GLOBEX_README) == GLOBEX_TEXT
    with pytest.raises(KeyError):
        plain.fetch_page("https://github.com/globex/pay#9")


def test_classify_without_a_cache_matches_the_healthy_classifier() -> None:
    from btm.variants.A5.classifier import classify

    plain = FakeModel()
    healthy = FakeModel()
    result, _ = classify(globex(), taxonomy(), plain, run_id="r0")
    expected, _ = healthy_classify(globex(), taxonomy(), healthy, run_id="r0")
    assert plain.prompts == healthy.prompts
    # Cada árbol define su propia `Classification`, así que se comparan valores.
    assert result.model_dump() == expected.model_dump()


def test_without_collisions_the_batch_matches_the_healthy_system(tmp_path: Path) -> None:
    root = disjoint_corpus(tmp_path)
    snapshots = [acme(), mesh()]

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
        ["acme--pay", "globex--pay"], root, loaded_taxonomy.load(TAXONOMY_PATH), model
    )
    assert [row.slug for row in rows] == ["acme--pay", "globex--pay"]
    assert ACME_TEXT in model.prompts[1]


# --- vocabulario --------------------------------------------------------


FORBIDDEN = (
    "avería", "averia", "bug", "escenario", "experimento", "variante",
    "estocástico", "estocastico", "envenenad", "contaminad", "contamina",
    "colisión", "colision", "arnés", "arnes", "harness",
)

DELIVERED = (
    Path(__file__).parents[1] / "src" / "btm" / "system",
    Path(__file__).parents[1] / "src" / "btm" / "variants",
)


def delivered_files() -> list[Path]:
    return sorted(path for root in DELIVERED for path in root.rglob("*.py"))


def test_nothing_that_ships_names_the_work_it_belongs_to() -> None:
    files = delivered_files()
    assert len(files) > 10
    for path in files:
        body = path.read_text(encoding="utf-8").lower()
        for word in FORBIDDEN:
            assert word not in body, (path.name, word)
        assert not re.search(r"\ba[1-5]\b", body), path.name


def test_nothing_that_ships_carries_the_log_trimmer() -> None:
    for path in delivered_files():
        body = path.read_text(encoding="utf-8")
        assert "POOR_KINDS" not in body, path.name
        assert "def poor(" not in body, path.name
