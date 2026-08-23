import json
from pathlib import Path

from btm.system.corpus import RepoSnapshot, load_all, load_snapshot


def write_snapshot(root: Path, slug: str, description: str | None) -> None:
    payload = {
        "slug": slug,
        "name": slug,
        "description": description,
        "documents": [
            {
                "url": f"https://example.invalid/{slug}/readme",
                "title": "README",
                "text": "Un cliente en Python para la API de un proveedor de pagos.",
                "kind": "readme",
            }
        ],
    }
    path = root / slug
    path.mkdir(parents=True)
    (path / "snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def test_loads_a_snapshot_with_its_documents(tmp_path: Path) -> None:
    write_snapshot(tmp_path, "acme-pay", "Cliente de pagos")
    snapshot = load_snapshot("acme-pay", tmp_path)
    assert isinstance(snapshot, RepoSnapshot)
    assert snapshot.description == "Cliente de pagos"
    assert snapshot.documents[0].kind == "readme"


def test_description_may_be_absent(tmp_path: Path) -> None:
    write_snapshot(tmp_path, "sin-descripcion", None)
    assert load_snapshot("sin-descripcion", tmp_path).description is None


def test_load_all_is_sorted_by_slug(tmp_path: Path) -> None:
    write_snapshot(tmp_path, "zeta", "z")
    write_snapshot(tmp_path, "alfa", "a")
    assert [s.slug for s in load_all(tmp_path)] == ["alfa", "zeta"]
