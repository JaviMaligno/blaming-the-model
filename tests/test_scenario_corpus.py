"""Las comprobaciones que tiene que pasar el corpus del escenario."""

from btm.harness.scenario_corpus import (
    MIN_SHARED_URLS,
    UNSTABLE,
    Pair,
    audit,
    filler_slugs,
    url_collisions,
)
from btm.system.corpus import Document, RepoSnapshot


def snap(slug: str, short_name: str, documents: int = 6) -> RepoSnapshot:
    return RepoSnapshot(
        slug=slug,
        name=short_name,
        description=None,
        documents=[
            Document(
                url=f"https://github.com/{short_name}#{i}",
                title=f"Sección {i}",
                text=f"Texto de {slug}, sección {i}.",
                kind="readme",
            )
            for i in range(documents)
        ],
    )


PAIR = Pair(name="orion", donor="pinterest--orion", victim="orion-rs--orion")


def test_distinct_short_names_share_no_url() -> None:
    assert url_collisions([snap("a--uno", "uno"), snap("b--dos", "dos")]) == {}


def test_a_shared_short_name_shows_up_as_shared_urls() -> None:
    shared = url_collisions([snap("pinterest--orion", "orion"), snap("orion-rs--orion", "orion")])
    assert len(shared) == 6
    assert shared["https://github.com/orion#0"] == ["orion-rs--orion", "pinterest--orion"]


def test_a_pair_that_collides_and_filler_that_does_not_passes() -> None:
    report = audit(
        [snap("pinterest--orion", "orion"), snap("orion-rs--orion", "orion"), snap("t--wurzel", "wurzel")],
        [PAIR],
    )
    assert report.shared_within_pair == {"orion": 6}
    assert report.stray == {}
    assert report.ok


def test_filler_colliding_with_a_pair_member_is_reported() -> None:
    report = audit(
        [snap("pinterest--orion", "orion"), snap("orion-rs--orion", "orion"), snap("otro--orion", "orion")],
        [PAIR],
    )
    assert not report.ok
    assert report.stray
    assert all("otro--orion" in slugs for slugs in report.stray.values())


def test_two_filler_repos_colliding_with_each_other_are_reported() -> None:
    report = audit(
        [snap("pinterest--orion", "orion"), snap("orion-rs--orion", "orion"),
         snap("a--vega", "vega"), snap("b--vega", "vega")],
        [PAIR],
    )
    assert not report.ok
    assert sorted({s for slugs in report.stray.values() for s in slugs}) == ["a--vega", "b--vega"]


def test_a_pair_with_too_few_shared_urls_fails() -> None:
    few = MIN_SHARED_URLS - 1
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
