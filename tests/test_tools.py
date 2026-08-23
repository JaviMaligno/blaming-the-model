from pathlib import Path

import pytest

from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy
from btm.system.tools import ToolBox

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"


def tied_snapshot() -> RepoSnapshot:
    # Cinco documentos, los tres primeros con los mismos tokens: empates seguros.
    texts = ["pagos api cliente", "pagos api cliente", "pagos api cliente",
             "guia de instalacion", "notas de version"]
    return RepoSnapshot(
        slug="acme",
        name="acme",
        description=None,
        documents=[
            Document(url=f"https://x.invalid/{i}", title=str(i), text=text, kind="docs")
            for i, text in enumerate(texts)
        ],
    )


@pytest.fixture
def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


def test_healthy_search_is_stable_across_run_ids(taxonomy: Taxonomy) -> None:
    orders = {
        tuple(h.url for h in ToolBox(tied_snapshot(), taxonomy, run_id=r).search("pagos api"))
        for r in ("r0", "r1", "r2", "r3")
    }
    assert len(orders) == 1, "el sistema sano no puede depender del run_id"


def test_best_matches_come_first(taxonomy: Taxonomy) -> None:
    hits = ToolBox(tied_snapshot(), taxonomy).search("pagos api")
    assert [h.url for h in hits[:3]] == [f"https://x.invalid/{i}" for i in range(3)]


def test_fetch_page_returns_the_document_text(taxonomy: Taxonomy) -> None:
    assert ToolBox(tied_snapshot(), taxonomy).fetch_page("https://x.invalid/0") == "pagos api cliente"


def test_fetch_page_rejects_unknown_url(taxonomy: Taxonomy) -> None:
    with pytest.raises(KeyError):
        ToolBox(tied_snapshot(), taxonomy).fetch_page("https://x.invalid/nope")


def test_lookup_taxonomy_returns_name_and_description(taxonomy: Taxonomy) -> None:
    assert ToolBox(tied_snapshot(), taxonomy).lookup_taxonomy("business.payments")["name"] == "Pagos"
