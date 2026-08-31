"""Clasificación de un lote de repositorios en una sola pasada.

Los snapshots no cambian mientras la pasada está en marcha, así que las páginas
se leen una vez y se conservan durante todo el lote en vez de volver a disco
por cada repositorio.
"""

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

from .classifier import classify
from btm.system.corpus import load_snapshot
from btm.system.model import Model
from .pages import PageCache
from btm.system.taxonomy import Taxonomy


class BatchRow(BaseModel):
    """Lo que el lote reporta de cada repositorio."""

    slug: str
    code: str
    confidence: float
    justification: str


def run_batch(
    slugs: Iterable[str],
    corpus_root: Path,
    taxonomy: Taxonomy,
    model: Model,
) -> list[BatchRow]:
    """Clasifica los repositorios del lote reutilizando las páginas ya leídas."""
    pages = PageCache()
    rows: list[BatchRow] = []
    for slug in slugs:
        snapshot = load_snapshot(slug, corpus_root)
        result, _ = classify(snapshot, taxonomy, model, run_id=slug, page_cache=pages)
        rows.append(
            BatchRow(
                slug=slug,
                code=result.code,
                confidence=result.confidence,
                justification=result.justification,
            )
        )
    return rows


def main(model: Model, argv: list[str] | None = None) -> None:
    """Lanza un lote desde la línea de comandos.

    El cliente del modelo lo inyecta el proceso que arranca el lote, que es
    quien tiene las credenciales del despliegue en uso.
    """
    parser = argparse.ArgumentParser(prog="classify-batch")
    parser.add_argument("slugs", nargs="+")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    args = parser.parse_args(argv)

    # Un repositorio repetido en la lista se clasifica una sola vez.
    pending = set(args.slugs)
    for row in run_batch(pending, args.corpus, Taxonomy.load(args.taxonomy), model):
        print(json.dumps(row.model_dump(), ensure_ascii=False))
