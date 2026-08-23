"""Lectura del snapshot local de repositorios.

Cada repositorio se guarda como un directorio con un `snapshot.json` que
contiene sus metadatos y los documentos capturados.
"""

import json
from pathlib import Path

from pydantic import BaseModel


class Document(BaseModel):
    """Un documento capturado de un repositorio."""

    url: str
    title: str
    text: str
    kind: str


class RepoSnapshot(BaseModel):
    """Un repositorio con sus metadatos y sus documentos.

    El registro de origen no siempre trae descripción, por lo que
    `description` puede venir vacía.
    """

    slug: str
    name: str
    description: str | None = None
    documents: list[Document]


def load_snapshot(slug: str, root: Path) -> RepoSnapshot:
    """Lee el snapshot de un repositorio por su slug."""
    payload = json.loads((root / slug / "snapshot.json").read_text(encoding="utf-8"))
    return RepoSnapshot.model_validate(payload)


def load_all(root: Path) -> list[RepoSnapshot]:
    """Lee todos los snapshots bajo `root`, ordenados por slug."""
    slugs = sorted(p.name for p in root.iterdir() if (p / "snapshot.json").exists())
    return [load_snapshot(slug, root) for slug in slugs]
