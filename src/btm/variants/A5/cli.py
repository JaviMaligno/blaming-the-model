"""Clasificación de un único repositorio desde la línea de comandos.

    python -m classify <slug> --corpus data/corpus

Cada invocación lee las páginas que necesita y termina: no hay nada que
conservar cuando el proceso se acaba.
"""

import argparse
import json
from pathlib import Path

from .classifier import Classification, classify
from btm.system.corpus import load_snapshot
from btm.system.model import Model
from .pages import PageCache
from btm.system.taxonomy import Taxonomy
from btm.system.trace import Trace


def run_one(
    slug: str,
    corpus_root: Path,
    taxonomy: Taxonomy,
    model: Model,
) -> tuple[Classification, Trace]:
    """Clasifica un repositorio y devuelve el resultado junto con su traza."""
    snapshot = load_snapshot(slug, corpus_root)
    return classify(snapshot, taxonomy, model, run_id=slug, page_cache=PageCache())


def main(model: Model, argv: list[str] | None = None) -> None:
    """Clasifica el repositorio que se pida y escribe el resultado por salida estándar.

    El cliente del modelo lo inyecta el proceso que arranca la corrida, que es
    quien tiene las credenciales del despliegue en uso.
    """
    parser = argparse.ArgumentParser(prog="classify")
    parser.add_argument("slug")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--trace", type=Path, help="fichero donde volcar la traza")
    args = parser.parse_args(argv)

    result, trace = run_one(args.slug, args.corpus, Taxonomy.load(args.taxonomy), model)
    if args.trace is not None:
        args.trace.write_text(trace.to_jsonl(), encoding="utf-8")
    print(json.dumps(result.model_dump(), ensure_ascii=False))
