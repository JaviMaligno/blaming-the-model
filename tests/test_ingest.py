"""Lo que la captura garantiza sobre las URLs que emite."""

import pytest

import btm.harness.ingest as ingest

SECTION = "Texto de sección con longitud más que suficiente para superar el mínimo. " * 2
README = "\n".join(f"## Sección {i}\n{SECTION}" for i in range(6))
EXTRA = "Guía de contribución con longitud más que suficiente para superar el mínimo. " * 2


@pytest.fixture
def github(monkeypatch):
    """Sustituye las dos llamadas a la API por un registro en memoria."""
    registry: dict[str, str] = {}

    def _gh(path: str) -> dict | None:
        full_name = path.removeprefix("repos/")
        if full_name not in registry:
            return None
        return {
            "name": registry[full_name],
            "default_branch": "main",
            "html_url": f"https://github.com/{full_name}",
            "description": "Un proyecto cualquiera",
            "stargazers_count": 7,
        }

    def _raw(full_name: str, branch: str, path: str) -> str | None:
        if path.lower() == "readme.md":
            return README
        if path == "CONTRIBUTING.md":
            return EXTRA
        return None

    monkeypatch.setattr(ingest, "_gh", _gh)
    monkeypatch.setattr(ingest, "_raw", _raw)
    return registry


def urls(snapshot: dict, kind: str) -> list[str]:
    return [d["url"] for d in snapshot["documents"] if d["kind"] == kind]


def test_document_urls_carry_the_owner(github) -> None:
    github["pinterest/orion"] = "orion"
    snapshot = ingest.capture("pinterest/orion")
    assert urls(snapshot, "readme")[0] == "https://github.com/pinterest/orion#0"
    assert urls(snapshot, "docs") == [
        "https://github.com/pinterest/orion/blob/main/CONTRIBUTING.md"
    ]
    assert snapshot["slug"] == "pinterest--orion"
    assert snapshot["source_url"] == "https://github.com/pinterest/orion"


def test_capture_has_no_mode_that_drops_the_owner(github) -> None:
    """El modo que emitía URLs sin owner se retiró; no queda forma de pedirlo."""
    github["pinterest/orion"] = "orion"
    with pytest.raises(TypeError):
        ingest.capture("pinterest/orion", short_name_urls=True)


def test_two_projects_with_the_same_short_name_share_no_url(github) -> None:
    github["pinterest/orion"] = "orion"
    github["orion-rs/orion"] = "orion"
    a, b = (ingest.capture(n) for n in ("pinterest/orion", "orion-rs/orion"))
    assert not {d["url"] for d in a["documents"]} & {d["url"] for d in b["documents"]}


def test_two_projects_with_the_same_short_name_share_name_and_section_indices(github) -> None:
    """Lo único que dos homónimos tienen en común es el nombre y la numeración."""
    github["pinterest/orion"] = "orion"
    github["orion-rs/orion"] = "orion"
    a, b = (ingest.capture(n) for n in ("pinterest/orion", "orion-rs/orion"))
    assert a["name"] == b["name"]
    shared = min(len(a["documents"]), len(b["documents"]))
    assert shared >= 3


def test_projects_with_different_short_names_never_collide(github) -> None:
    github["pinterest/orion"] = "orion"
    github["telekom/wurzel"] = "wurzel"
    a = ingest.capture("pinterest/orion")
    b = ingest.capture("telekom/wurzel")
    assert a["name"] != b["name"]
    assert not {d["url"] for d in a["documents"]} & {d["url"] for d in b["documents"]}
