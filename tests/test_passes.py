"""Las pasadas del lote y el registrador que anota qué página recibió cada una.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. Los snapshots
se construyen en memoria, así que la suite corre sin red y sin modelo.
"""

import json
import subprocess
import sys
from pathlib import Path

from btm.harness.passes import (
    PassResult,
    load_batch,
    run_pass,
    set_order,
    sha256,
    solo_labels,
)
from tests.test_a5 import (
    ACME_README,
    ACME_TEXT,
    GLOBEX_README,
    GLOBEX_TEXT,
    FakeModel,
    acme,
    colliding_corpus,
    disjoint_corpus,
    globex,
)

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"


def pass_over(corpus: Path, dest: Path, model=None, **kwargs) -> PassResult:
    return run_pass(
        "p0",
        seed=0,
        slugs=sorted(p.name for p in corpus.iterdir()),
        corpus=corpus,
        taxonomy_path=TAXONOMY_PATH,
        model=model or FakeModel(),
        dest=dest,
        **kwargs,
    )


# --- el registrador -----------------------------------------------------


def test_the_recorder_notes_who_the_served_page_really_belonged_to(tmp_path: Path) -> None:
    result = pass_over(colliding_corpus(tmp_path), tmp_path / "tree")
    # Los dos homónimos piden su sección `#0`, cada uno por su propia url.
    shared = [s for p in result.projects for s in p.served if s.url.endswith("#0")]
    assert len(shared) == 2
    owners = {s.owner for s in shared}
    assert len(owners) == 1, "la primera lectura fija el propietario"
    owner = owners.pop()
    borrower = next(s for s in shared if s.slug != owner)
    assert borrower.foreign is True
    assert borrower.sha256 == sha256(ACME_TEXT if owner == "acme--pay" else GLOBEX_TEXT)
    assert borrower.sha256 != borrower.own_sha256
    assert borrower.in_context is True


def test_the_recorder_marks_as_its_own_what_each_project_did_publish(tmp_path: Path) -> None:
    result = pass_over(disjoint_corpus(tmp_path), tmp_path / "tree")
    served = [s for p in result.projects for s in p.served]
    assert served
    assert all(s.foreign is False for s in served)
    assert all(s.sha256 == s.own_sha256 for s in served)


def test_a_pass_records_the_order_and_the_prompt_of_every_project(tmp_path: Path) -> None:
    result = pass_over(colliding_corpus(tmp_path), tmp_path / "tree")
    assert sorted(result.order) == ["acme--pay", "globex--pay"]
    assert [p.slug for p in result.projects] == result.order
    for project in result.projects:
        assert project.prompt_bytes > 0
        assert project.context_urls
        assert '"kind": "final"' in project.trace_jsonl


# --- la clave reparada --------------------------------------------------


def test_with_the_repaired_key_nobody_reads_a_neighbours_page(tmp_path: Path) -> None:
    result = pass_over(colliding_corpus(tmp_path), tmp_path / "tree", keyed=True)
    served = [s for p in result.projects for s in p.served]
    assert served
    assert all(s.foreign is False for s in served)


def test_the_repaired_key_gives_each_project_the_prompt_of_its_single_run(tmp_path: Path) -> None:
    corpus = colliding_corpus(tmp_path)
    alone = solo_labels(sorted(p.name for p in corpus.iterdir()), corpus, TAXONOMY_PATH,
                        lambda: FakeModel(), workers=1)
    repaired = pass_over(corpus, tmp_path / "tree", keyed=True)
    assert {p.slug: p.prompt_sha256 for p in repaired.projects} == {
        r.slug: r.prompt_sha256 for r in alone
    }


def test_without_the_repair_someone_gets_a_prompt_that_is_not_its_own(tmp_path: Path) -> None:
    corpus = colliding_corpus(tmp_path)
    alone = {r.slug: r.prompt_sha256 for r in solo_labels(
        sorted(p.name for p in corpus.iterdir()), corpus, TAXONOMY_PATH,
        lambda: FakeModel(), workers=1)}
    shared = pass_over(corpus, tmp_path / "tree")
    changed = [p.slug for p in shared.projects if p.prompt_sha256 != alone[p.slug]]
    assert len(changed) == 1


# --- el orden del lote --------------------------------------------------


def test_the_batch_order_is_the_one_the_entry_point_derives(tmp_path: Path) -> None:
    slugs = sorted(p.name for p in colliding_corpus(tmp_path).iterdir())
    assert sorted(set_order(slugs)) == slugs


def test_the_same_seed_gives_the_same_order_in_two_processes() -> None:
    slugs = [f"repo-{i:02d}" for i in range(40)]
    orders = set()
    for _ in range(2):
        out = subprocess.run(
            [sys.executable, "-m", "btm.harness.passes", "order", "--slugs", json.dumps(slugs)],
            capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": "12345", "PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
            cwd=Path(__file__).parents[1],
        )
        orders.add(out.stdout.strip())
    assert len(orders) == 1


def test_a_different_seed_gives_a_different_order() -> None:
    slugs = [f"repo-{i:02d}" for i in range(40)]
    orders = set()
    for seed in ("1", "2", "3", "4"):
        out = subprocess.run(
            [sys.executable, "-m", "btm.harness.passes", "order", "--slugs", json.dumps(slugs)],
            capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": seed, "PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
            cwd=Path(__file__).parents[1],
        )
        orders.add(out.stdout.strip())
    assert len(orders) > 1


# --- el árbol reparado no se entrega ------------------------------------


def test_the_repaired_tree_keys_pages_by_project_and_section(tmp_path: Path) -> None:
    batch = load_batch(tmp_path / "tree", keyed=True)
    cache = batch.PageCache()
    assert cache.get_or_load(ACME_README, acme()) == ACME_TEXT
    assert cache.get_or_load(GLOBEX_README, globex()) == GLOBEX_TEXT
