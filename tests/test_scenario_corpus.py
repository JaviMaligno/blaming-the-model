"""Las comprobaciones que tiene que pasar el corpus del escenario."""

from pathlib import Path

from btm.harness.scenario_corpus import (
    MIN_SHARED_PAGES,
    PAIRS,
    UNSTABLE,
    Pair,
    audit,
    filler_slugs,
    key_collisions,
    url_collisions,
)
from btm.system.corpus import Document, RepoSnapshot, load_all


def snap(slug: str, short_name: str, documents: int = 6) -> RepoSnapshot:
    """Un snapshot como los que emite la captura: la URL lleva el owner."""
    full_name = slug.replace("--", "/", 1)
    return RepoSnapshot(
        slug=slug,
        name=short_name,
        description=None,
        documents=[
            Document(
                url=f"https://github.com/{full_name}#{i}",
                title=f"Sección {i}",
                text=f"Texto de {slug}, sección {i}.",
                kind="readme",
            )
            for i in range(documents)
        ],
    )


PAIR = Pair(name="orion", donor="pinterest--orion", victim="orion-rs--orion")
HOMONYMS = [snap("pinterest--orion", "orion"), snap("orion-rs--orion", "orion")]


def test_no_two_projects_share_a_url_not_even_two_homonyms() -> None:
    assert url_collisions(HOMONYMS) == {}
    assert url_collisions([snap("a--uno", "uno"), snap("b--dos", "dos")]) == {}


def test_distinct_short_names_share_no_page_key() -> None:
    assert key_collisions([snap("a--uno", "uno"), snap("b--dos", "dos")]) == {}


def test_a_shared_short_name_shows_up_as_shared_page_keys() -> None:
    shared = key_collisions(HOMONYMS)
    assert len(shared) == 6
    assert shared["orion#0"] == ["orion-rs--orion", "pinterest--orion"]


def extra(slug: str) -> Document:
    """Un documento sin fragmento en la url, como los `CONTRIBUTING.md`."""
    return Document(
        url=f"https://github.com/{slug.replace('--', '/', 1)}/blob/main/CONTRIBUTING.md",
        title="CONTRIBUTING.md",
        text=f"Guía de {slug}.",
        kind="docs",
    )


def test_a_document_without_fragment_never_collides_between_homonyms() -> None:
    """Sin fragmento la clave cae en la url entera, que sí lleva owner."""
    donor, victim = (s.model_copy(deep=True) for s in HOMONYMS)
    donor.documents.append(extra(donor.slug))
    victim.documents.append(extra(victim.slug))
    shared = key_collisions([donor, victim])
    assert len(shared) == 6
    assert all(key.removeprefix("orion#").isdigit() for key in shared)


def test_a_pair_that_shares_keys_and_filler_that_does_not_passes() -> None:
    report = audit([*HOMONYMS, snap("t--wurzel", "wurzel")], [PAIR])
    assert report.shared_within_pair == {"orion": 6}
    assert report.stray == {}
    assert report.shared_urls == {}
    assert report.ok


def test_filler_sharing_the_name_of_a_pair_member_is_reported() -> None:
    report = audit([*HOMONYMS, snap("otro--orion", "orion")], [PAIR])
    assert not report.ok
    assert report.stray
    assert all("otro--orion" in slugs for slugs in report.stray.values())


def test_two_filler_repos_sharing_a_name_are_reported() -> None:
    report = audit([*HOMONYMS, snap("a--vega", "vega"), snap("b--vega", "vega")], [PAIR])
    assert not report.ok
    assert sorted({s for slugs in report.stray.values() for s in slugs}) == ["a--vega", "b--vega"]


def test_a_repeated_url_fails_the_audit_even_inside_a_pair() -> None:
    """La coincidencia vive en la clave; en la URL sería un delator."""
    donor, victim = HOMONYMS
    victim = victim.model_copy(deep=True)
    victim.documents[0].url = donor.documents[0].url
    report = audit([donor, victim], [PAIR])
    assert not report.ok
    assert report.shared_urls == {
        "https://github.com/pinterest/orion#0": ["orion-rs--orion", "pinterest--orion"]
    }


def test_a_pair_with_too_few_shared_pages_fails() -> None:
    few = MIN_SHARED_PAGES - 1
    report = audit(
        [snap("pinterest--orion", "orion", documents=few), snap("orion-rs--orion", "orion")],
        [PAIR],
    )
    assert report.shared_within_pair == {"orion": few}
    assert report.stray == {}
    assert not report.ok


def test_a_missing_pair_member_fails() -> None:
    report = audit([snap("pinterest--orion", "orion")], [PAIR])
    assert not report.ok
    assert report.missing == ["orion-rs--orion"]


def test_filler_leaves_out_the_repositories_that_oscillate(tmp_path) -> None:
    for slug in ("telekom--wurzel", *UNSTABLE):
        (tmp_path / slug).mkdir()
        (tmp_path / slug / "snapshot.json").write_text("{}", encoding="utf-8")
    assert filler_slugs(tmp_path) == ["telekom--wurzel"]


def test_the_declared_pairs_are_disjoint_and_uniquely_named() -> None:
    """Un proyecto pertenece a un par y sólo a uno, y cada nombre a un par."""
    members = [slug for pair in PAIRS for slug in (pair.donor, pair.victim)]
    assert len(members) == len(set(members))
    assert len(PAIRS) == len({pair.name for pair in PAIRS})


def test_every_declared_pair_member_lives_in_the_scenario_corpus() -> None:
    root = Path("data/scenario")
    for pair in PAIRS:
        for slug in (pair.donor, pair.victim):
            assert (root / slug / "snapshot.json").exists(), slug


def test_the_scenario_corpus_passes_its_own_audit() -> None:
    assert audit(load_all(Path("data/scenario")), PAIRS).ok
