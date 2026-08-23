from pathlib import Path

import pytest

from btm.system.taxonomy import Taxonomy

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"


@pytest.fixture
def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


def test_leaf_knows_its_parent(taxonomy: Taxonomy) -> None:
    node = taxonomy.get("business.payments")
    assert node.name == "Pagos"
    assert node.parent == "business"


def test_every_leaf_code_is_prefixed_by_its_parent(taxonomy: Taxonomy) -> None:
    for leaf in taxonomy.leaves():
        assert leaf.parent is not None
        assert leaf.code.startswith(f"{leaf.parent}.")


def test_the_colliding_classes_exist(taxonomy: Taxonomy) -> None:
    assert taxonomy.get("business.payments")
    assert taxonomy.get("devtools.libraries")


def test_unknown_code_raises(taxonomy: Taxonomy) -> None:
    with pytest.raises(KeyError):
        taxonomy.get("business.nonexistent")
