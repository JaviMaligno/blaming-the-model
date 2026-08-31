"""Pasadas del lote sobre el corpus del escenario, con registro de la verdad.

Esto es arnés: nunca se entrega. El lote entregado —`batch.main` del árbol
materializado de A5— corre aquí tal cual, sin una línea cambiada; lo único que
se le añade desde fuera es un envoltorio sobre su caché de páginas que anota,
cada vez que se sirve un documento, el sha256 del texto que salió, de quién era
realmente y si entró en la ventana de contexto. Esa anotación es la clave de
corrección, y por eso vive fuera del paquete.

El orden del lote no lo decide el arnés: lo decide `set(args.slugs)` dentro del
propio `main`, y por tanto `PYTHONHASHSEED`. Cada pasada se lanza en un proceso
distinto con un seed distinto, y `order` reproduce ese mismo orden sin gastar
una llamada al modelo.

Con `--keyed` se materializa el mismo árbol con `pages.py` sustituido por el de
`btm/harness/fix/`, que compone la clave con `(slug, url)`. Es la prueba de
arreglo: mismas pasadas, mismos seeds, misma inferencia.
"""

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from btm.harness.model import AzureModel
from btm.harness.variants import _rewrite_imports, materialise

FIX_DIR = Path(__file__).parent / "fix"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Served(BaseModel):
    """Un documento que la caché entregó a una corrida."""

    slug: str
    url: str
    sha256: str
    owner: str
    foreign: bool
    own_sha256: str | None
    text_differs: bool
    in_context: bool = False


class ProjectRun(BaseModel):
    """Lo que una corrida del lote hizo con un proyecto."""

    slug: str
    position: int
    code: str
    confidence: float
    justification: str
    context_urls: list[str]
    prompt_sha256: str
    prompt_bytes: int
    prompt: str
    served: list[Served]
    trace_jsonl: str

    @property
    def contaminated(self) -> bool:
        return any(s.foreign and s.in_context and s.text_differs for s in self.served)


class PassResult(BaseModel):
    """Una pasada completa del lote."""

    pass_id: str
    hashseed: int
    keyed: bool = False
    order: list[str]
    projects: list[ProjectRun]

    def by_slug(self) -> dict[str, ProjectRun]:
        return {p.slug: p for p in self.projects}


def set_order(slugs: list[str]) -> list[str]:
    """El orden en el que el lote recorrerá los proyectos.

    Es literalmente lo que hace el punto de entrada entregado al deduplicar su
    lista de argumentos, y depende de `PYTHONHASHSEED`.
    """
    return list(set(slugs))


def load_batch(dest: Path, *, keyed: bool = False):
    """Importa el módulo de lote del árbol materializado, sano o reparado."""
    package = materialise("A5", dest)
    if keyed:
        (package / "pages.py").write_text(
            _rewrite_imports((FIX_DIR / "pages.py").read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    name = "btm_system_keyed" if keyed else "btm_system_shared"
    for cached in [k for k in sys.modules if k == name or k.startswith(f"{name}.")]:
        del sys.modules[cached]
    spec = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    root = importlib.util.module_from_spec(spec)
    sys.modules[name] = root
    spec.loader.exec_module(root)
    return importlib.import_module(f"{name}.batch")


def _recording(base: type, log: list[Served]) -> type:
    """La caché del árbol entregado, envuelta para que deje constancia."""

    class RecordingPageCache(base):
        def __init__(self) -> None:
            super().__init__()
            # Quién presentó por primera vez cada texto concreto de cada url.
            # No basta con la url: con la clave reparada dos proyectos guardan
            # textos distintos bajo la misma, y cada uno es dueño del suyo.
            self._owner: dict[tuple[str, str], str] = {}

        def get_or_load(self, url: str, snapshot) -> str:
            text = super().get_or_load(url, snapshot)
            owner = self._owner.setdefault((url, sha256(text)), snapshot.slug)
            own = next((d.text for d in snapshot.documents if d.url == url), None)
            log.append(
                Served(
                    slug=snapshot.slug,
                    url=url,
                    sha256=sha256(text),
                    owner=owner,
                    foreign=owner != snapshot.slug,
                    own_sha256=sha256(own) if own is not None else None,
                    text_differs=own is not None and own != text,
                )
            )
            return text

    return RecordingPageCache


def _events(trace_jsonl: str) -> list[dict]:
    return [json.loads(line) for line in trace_jsonl.strip().splitlines()]


def _payload(events: list[dict], kind: str, field: str, default=None):
    for event in events:
        if event["kind"] == kind:
            return event["payload"][field]
    return default


def run_pass(
    pass_id: str,
    *,
    seed: int,
    slugs: list[str],
    corpus: Path,
    taxonomy_path: Path,
    model,
    dest: Path,
    keyed: bool = False,
) -> PassResult:
    """Corre el lote entregado de punta a punta y devuelve lo que pasó dentro."""
    batch = load_batch(dest, keyed=keyed)
    log: list[Served] = []
    batch.PageCache = _recording(batch.PageCache, log)

    inner = batch.classify
    projects: list[ProjectRun] = []

    def watched(snapshot, taxonomy, client, *, run_id, **kwargs):
        mark = len(log)
        result, trace = inner(snapshot, taxonomy, client, run_id=run_id, **kwargs)
        events = _events(trace.to_jsonl())
        context = _payload(events, "context_documents", "urls", []) or []
        prompt = _payload(events, "model_message", "prompt", "") or ""
        served = log[mark:]
        for entry in served:
            entry.in_context = entry.url in context
        projects.append(
            ProjectRun(
                slug=snapshot.slug,
                position=len(projects),
                code=result.code,
                confidence=result.confidence,
                justification=result.justification,
                context_urls=context,
                prompt_sha256=sha256(prompt),
                prompt_bytes=len(prompt.encode("utf-8")),
                prompt=prompt,
                served=served,
                trace_jsonl=trace.to_jsonl(),
            )
        )
        return result, trace

    batch.classify = watched
    argv = [*slugs, "--corpus", str(corpus), "--taxonomy", str(taxonomy_path)]
    with contextlib.redirect_stdout(io.StringIO()):
        batch.main(model, argv)

    return PassResult(
        pass_id=pass_id,
        hashseed=seed,
        keyed=keyed,
        order=[p.slug for p in projects],
        projects=projects,
    )


class SoloRun(BaseModel):
    """Lo que devuelve un proyecto clasificado a solas."""

    slug: str
    code: str
    confidence: float
    justification: str
    context_urls: list[str]
    prompt_sha256: str
    prompt_bytes: int
    prompt: str
    trace_jsonl: str


def solo_labels(
    slugs: list[str],
    corpus: Path,
    taxonomy_path: Path,
    make_model: Callable[[], object],
    *,
    workers: int = 6,
    dest: Path | None = None,
) -> list[SoloRun]:
    """Clasifica cada proyecto por separado, como hace el punto de entrada suelto."""
    work = dest or Path(".work/a5-solo")
    batch = load_batch(work)
    cli = importlib.import_module(f"{batch.__name__.rsplit('.', 1)[0]}.cli")
    taxonomy_cls = importlib.import_module(f"{batch.__name__.rsplit('.', 1)[0]}.taxonomy").Taxonomy
    taxonomy = taxonomy_cls.load(taxonomy_path)

    def one(slug: str) -> SoloRun:
        result, trace = cli.run_one(slug, corpus, taxonomy, make_model())
        events = _events(trace.to_jsonl())
        prompt = _payload(events, "model_message", "prompt", "") or ""
        return SoloRun(
            slug=slug,
            code=result.code,
            confidence=result.confidence,
            justification=result.justification,
            context_urls=_payload(events, "context_documents", "urls", []) or [],
            prompt_sha256=sha256(prompt),
            prompt_bytes=len(prompt.encode("utf-8")),
            prompt=prompt,
            trace_jsonl=trace.to_jsonl(),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, slugs))


# --- línea de comandos --------------------------------------------------


def corpus_slugs(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if (p / "snapshot.json").exists())


class _Stub:
    """Un cliente que no llama a nadie: sirve para comparar contextos."""

    def complete(self, messages: list[dict]) -> str:
        return '{"code": "devtools.libraries", "confidence": 0.5, "justification": "-"}'


def _order(args: argparse.Namespace) -> None:
    slugs = json.loads(args.slugs) if args.slugs else corpus_slugs(args.corpus)
    print(json.dumps(set_order(slugs)))


def _run(args: argparse.Namespace) -> None:
    seed = int(os.environ.get("PYTHONHASHSEED", "-1"))
    if seed != args.seed:
        raise SystemExit(f"PYTHONHASHSEED={seed!r} no coincide con --seed {args.seed}")
    model = _Stub() if args.stub else AzureModel(deployment=args.deployment)
    result = run_pass(
        args.pass_id,
        seed=args.seed,
        slugs=corpus_slugs(args.corpus),
        corpus=args.corpus,
        taxonomy_path=args.taxonomy,
        model=model,
        dest=args.work / f"{args.pass_id}{'-keyed' if args.keyed else ''}",
        keyed=args.keyed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"{args.pass_id} seed={args.seed} keyed={args.keyed} -> {args.out}")


def _solo(args: argparse.Namespace) -> None:
    runs = solo_labels(
        corpus_slugs(args.corpus),
        args.corpus,
        args.taxonomy,
        lambda: _Stub() if args.stub else AzureModel(deployment=args.deployment),
        workers=args.workers,
        dest=args.work / "solo",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([r.model_dump() for r in runs], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(runs)} corridas sueltas -> {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-passes")
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--work", type=Path, default=Path(".work/a5"))
    parser.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    parser.add_argument("--stub", action="store_true")
    sub = parser.add_subparsers(dest="stage", required=True)

    order = sub.add_parser("order")
    order.add_argument("--slugs")
    order.set_defaults(fn=_order)

    run = sub.add_parser("run")
    run.add_argument("--pass-id", dest="pass_id", required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--keyed", action="store_true")
    run.add_argument("--out", type=Path, required=True)
    run.set_defaults(fn=_run)

    solo = sub.add_parser("solo")
    solo.add_argument("--out", type=Path, required=True)
    solo.add_argument("--workers", type=int, default=6)
    solo.set_defaults(fn=_solo)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
