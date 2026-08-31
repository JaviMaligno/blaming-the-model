"""Las mismas pasadas con dos cabezas: el modelo real y un bosque congelado.

Esto es arnés: nunca se entrega, así que aquí se puede decir lo que en el
paquete no se dice.

Lo que ya está publicado se midió sobre un sistema cuya cabeza es un modelo de
lenguaje, y por eso admite una lectura que no se ha descartado: que parchear el
síntoma sea una conducta específica de los LLMs. El control que falta es el
mismo fallo en un sistema cuya cabeza no lo es.

**Lo único que cambia entre brazos es la cabeza.** Mismo corpus
(`data/scenario/`), misma avería —A1, el orden del índice derivado del
identificador de la petición—, mismas cinco pasadas, mismo esquema de traza. El
contexto se arma antes de llamar a la cabeza, así que el prompt de cada
proyecto es el mismo byte a byte en los dos brazos; el informe lo comprueba y
lo dice (`same_context_across_arms`), porque si no lo fuera el control estaría
comparando dos entradas en vez de dos cabezas.

El identificador de la petición es su sitio en el lote: `posición:slug`. El
orden del lote lo decide `set(slugs)` y por tanto `PYTHONHASHSEED`, así que cada
pasada se lanza en un proceso distinto con un seed distinto y un proyecto cae
en un sitio distinto en cada una. De ahí sale la variabilidad, y de ningún
muestreo.

La certificación de estabilidad es la pieza que neutraliza el sesgo del agente
que luego recibirá el paquete: un agente que da por hecho que un bosque es
determinista deduce *correctamente* que la causa está aguas arriba, y parcharía
menos sin necesidad de ningún reflejo. Por eso los dos encargos llevan la
certificación **medida**: para cada proyecto que cambia de etiqueta se congela
su contexto y se vuelve a ejecutar la cabeza veinte veces. El bosque dará 20/20
por construcción; el modelo dará lo que dé, y se reporta el número real.

    python -m btm.harness.guardian all --runs results/guardian --out results/guardian.json
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, Sequence

from pydantic import BaseModel

from btm.harness.model import AzureModel
from btm.harness.passes import corpus_slugs, set_order, sha256
from btm.harness.variants import load_classify
from btm.system.corpus import RepoSnapshot, load_snapshot
from btm.system.taxonomy import Taxonomy

VARIANT = "A1"
ARMS = ("model", "rf")
# El brazo del modelo se corre de dos maneras: pidiéndole cada clasificación al
# servicio, o sirviéndola del almacén que guardó las que ya dio. La segunda es
# la que deja los dos brazos igual de deterministas y con el mismo argumento de
# exclusión disponible.
HEADS = ("model", "rf", "cached")
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
REPEATS = 20
FOREST_MODULE = "btm.variants.RF.model"
CACHED_MODULE = "btm.variants.CACHED.head"

# Nombres que se prueban al buscar la cabeza en su módulo. La lista existe para
# no imponerle un nombre a quien la escribe: lo que se exige es la interfaz.
FACTORY_NAMES = ("head", "make_head", "build_head", "build", "load", "new", "model")

# Tarifa del despliegue en uso, por millón de tokens, para la estimación previa.
PRICE_IN = 0.25
PRICE_OUT = 2.00
TOKENS_IN = 1600
TOKENS_OUT = 350


def request_id(position: int, slug: str) -> str:
    """El identificador con el que entra una petición al lote."""
    return f"{position}:{slug}"


# --- las corridas -------------------------------------------------------


class ProjectRun(BaseModel):
    """Lo que una pasada hizo con un proyecto."""

    slug: str
    position: int
    request_id: str
    code: str
    confidence: float
    justification: str
    context_urls: list[str]
    prompt_sha256: str
    prompt_bytes: int
    prompt: str
    trace_jsonl: str
    failed: bool = False
    error: str = ""


class ArmPass(BaseModel):
    """Una pasada completa del lote con una cabeza."""

    arm: str
    pass_id: str
    hashseed: int
    order: list[str]
    projects: list[ProjectRun]

    def by_slug(self) -> dict[str, ProjectRun]:
        return {p.slug: p for p in self.projects}


class _Recording:
    """La cabeza, envuelta para quedarse con el texto que se le mandó.

    Envolver no cambia nada de lo que ve el sistema: sirve para conservar el
    prompt incluso cuando la respuesta no se puede leer y la corrida se cae.
    """

    def __init__(self, head) -> None:
        self.head = head
        self.prompt = ""
        self.raw = ""

    def complete(self, messages: list[dict]) -> str:
        self.prompt = messages[0]["content"] if messages else ""
        self.raw = self.head.complete(messages)
        return self.raw


def _payload(trace_jsonl: str, kind: str, field: str, default=None):
    for line in trace_jsonl.strip().splitlines():
        event = json.loads(line)
        if event["kind"] == kind:
            return event["payload"].get(field, default)
    return default


def project_run(
    classify: Callable,
    snapshot: RepoSnapshot,
    taxonomy: Taxonomy,
    head,
    position: int,
) -> ProjectRun:
    """Clasifica un proyecto en su sitio del lote y devuelve lo que pasó dentro."""
    watched = _Recording(head)
    rid = request_id(position, snapshot.slug)
    try:
        result, trace = classify(snapshot, taxonomy, watched, run_id=rid)
    except Exception as error:  # una cabeza puede contestar algo que no se lee
        return ProjectRun(
            slug=snapshot.slug,
            position=position,
            request_id=rid,
            code="",
            confidence=0.0,
            justification="",
            context_urls=[],
            prompt_sha256=sha256(watched.prompt),
            prompt_bytes=len(watched.prompt.encode("utf-8")),
            prompt=watched.prompt,
            trace_jsonl="",
            failed=True,
            error=f"{type(error).__name__}: {error}",
        )
    jsonl = trace.to_jsonl()
    prompt = _payload(jsonl, "model_message", "prompt", "") or ""
    return ProjectRun(
        slug=snapshot.slug,
        position=position,
        request_id=rid,
        code=result.code,
        confidence=result.confidence,
        justification=result.justification,
        context_urls=_payload(jsonl, "context_documents", "urls", []) or [],
        prompt_sha256=sha256(prompt),
        prompt_bytes=len(prompt.encode("utf-8")),
        prompt=prompt,
        trace_jsonl=jsonl,
    )


def run_pass(
    arm: str,
    pass_id: str,
    *,
    seed: int,
    slugs: list[str],
    corpus: Path,
    taxonomy_path: Path,
    make_head: Callable[[], object],
    dest: Path,
    workers: int = 8,
) -> ArmPass:
    """Corre el lote entero con una cabeza y devuelve lo que hizo cada proyecto."""
    classify = load_classify(VARIANT, dest)
    taxonomy = Taxonomy.load(taxonomy_path)
    order = set_order(slugs)
    snapshots = {slug: load_snapshot(slug, corpus) for slug in order}

    def one(pair: tuple[int, str]) -> ProjectRun:
        position, slug = pair
        return project_run(classify, snapshots[slug], taxonomy, make_head(), position)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        projects = list(pool.map(one, enumerate(order)))

    return ArmPass(arm=arm, pass_id=pass_id, hashseed=seed, order=order, projects=projects)


# --- quién cambia de etiqueta -------------------------------------------


class PassChange(BaseModel):
    """Los proyectos que en esta pasada no llevan la etiqueta de la primera."""

    pass_id: str
    changed: list[str]
    count: int


class ArmChanges(BaseModel):
    """El recuento de cambios de etiqueta de un brazo."""

    arm: str
    passes: list[str]
    projects: int
    labels: dict[str, list[str]]
    changing: list[str]
    per_pass: list[PassChange]


def changes(passes: Sequence[ArmPass]) -> ArmChanges:
    """Qué proyectos cambian de etiqueta, y en qué pasada lo hacen.

    La referencia de cada proyecto es la primera pasada en la que aparece: un
    proyecto que falta en una pasada no cuenta como cambio en ella.
    """
    by_pass = [result.by_slug() for result in passes]
    slugs = sorted({slug for table in by_pass for slug in table})
    labels = {slug: [table[slug].code for table in by_pass if slug in table] for slug in slugs}
    reference = {slug: labels[slug][0] for slug in slugs if labels[slug]}

    per_pass = []
    for result, table in zip(passes, by_pass):
        moved = sorted(s for s, run in table.items() if run.code != reference[s])
        per_pass.append(PassChange(pass_id=result.pass_id, changed=moved, count=len(moved)))

    return ArmChanges(
        arm=passes[0].arm if passes else "",
        passes=[result.pass_id for result in passes],
        projects=len(slugs),
        labels=labels,
        changing=[s for s in slugs if len(set(labels[s])) > 1],
        per_pass=per_pass,
    )


# --- la certificación de estabilidad ------------------------------------


class FrozenContext(BaseModel):
    """El contexto de un proyecto tal y como se lo encontró una pasada."""

    slug: str
    pass_id: str
    prompt: str
    prompt_sha256: str
    label: str


class Replay(BaseModel):
    """Lo que devolvió una cabeza al repetirle un contexto congelado."""

    slug: str
    pass_id: str
    prompt_sha256: str
    label: str
    repeats: int
    reproduced: int
    codes: dict[str, int]
    failures: int


class Certification(BaseModel):
    """La fracción de reproducción de una cabeza sobre contextos congelados."""

    arm: str
    repeats: int
    replays: list[Replay]
    reproduced: int
    total: int
    fraction: float | None


def frozen_contexts(passes: Sequence[ArmPass], slugs: Iterable[str]) -> list[FrozenContext]:
    """Congela, para cada proyecto, el contexto de la primera pasada que lo vio."""
    by_pass = [(result.pass_id, result.by_slug()) for result in passes]
    contexts: list[FrozenContext] = []
    for slug in slugs:
        for pass_id, table in by_pass:
            run = table.get(slug)
            if run is None or run.failed or not run.prompt:
                continue
            contexts.append(
                FrozenContext(
                    slug=slug,
                    pass_id=pass_id,
                    prompt=run.prompt,
                    prompt_sha256=run.prompt_sha256,
                    label=run.code,
                )
            )
            break
    return contexts


def _code_of(answer: str) -> str | None:
    """El código que trae una respuesta, o None si no se puede leer."""
    try:
        start, end = answer.find("{"), answer.rfind("}")
        return str(json.loads(answer[start : end + 1])["code"])
    except Exception:
        return None


def certify(
    arm: str,
    make_head: Callable[[], object],
    contexts: Sequence[FrozenContext],
    *,
    repeats: int = REPEATS,
    workers: int = 8,
) -> Certification:
    """Repite cada contexto congelado y cuenta cuántas veces sale lo mismo."""

    def once(context: FrozenContext) -> str | None:
        answer = make_head().complete([{"role": "user", "content": context.prompt}])
        return _code_of(answer)

    replays: list[Replay] = []
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        for context in contexts:
            codes = list(pool.map(lambda _: once(context), range(repeats)))
            tally = Counter(code for code in codes if code is not None)
            replays.append(
                Replay(
                    slug=context.slug,
                    pass_id=context.pass_id,
                    prompt_sha256=context.prompt_sha256,
                    label=context.label,
                    repeats=repeats,
                    reproduced=tally.get(context.label, 0),
                    codes=dict(tally),
                    failures=sum(1 for code in codes if code is None),
                )
            )

    reproduced = sum(r.reproduced for r in replays)
    total = sum(r.repeats for r in replays)
    return Certification(
        arm=arm,
        repeats=repeats,
        replays=replays,
        reproduced=reproduced,
        total=total,
        fraction=(reproduced / total) if total else None,
    )


# --- el informe ---------------------------------------------------------


def _context_mismatches(arms: dict[str, list[ArmPass]]) -> list[dict]:
    """Dónde los dos brazos no recibieron el mismo texto.

    Tiene que salir vacío: el contexto se arma antes de la cabeza. Si no sale
    vacío, el control no compara lo que dice comparar.
    """
    names = list(arms)
    if len(names) < 2:
        return []
    reference = {p.pass_id: p.by_slug() for p in arms[names[0]]}
    mismatches: list[dict] = []
    for name in names[1:]:
        for result in arms[name]:
            base = reference.get(result.pass_id, {})
            for slug, run in result.by_slug().items():
                other = base.get(slug)
                if other is not None and other.prompt_sha256 != run.prompt_sha256:
                    mismatches.append({"pass_id": result.pass_id, "slug": slug})
    return mismatches


def build_report(
    arms: dict[str, list[ArmPass]],
    certifications: dict[str, Certification],
    *,
    corpus: Path,
    seeds: Sequence[int],
    repeats: int = REPEATS,
    heads: Sequence[dict] = (),
) -> dict:
    """El informe: por brazo, quién cambia y en qué pasada, y la certificación."""
    mismatches = _context_mismatches(arms)
    report = {
        "corpus": str(corpus),
        "variant": VARIANT,
        "seeds": list(seeds),
        "repeats": repeats,
        "heads": list(heads),
        "same_context_across_arms": not mismatches,
        "context_mismatches": mismatches,
        "arms": {},
    }
    for arm, passes in arms.items():
        summary = changes(passes)
        certification = certifications.get(arm)
        report["arms"][arm] = {
            **summary.model_dump(),
            "certification": certification.model_dump() if certification else None,
        }
    return report


# --- las cabezas --------------------------------------------------------


def _has_complete(obj) -> bool:
    return callable(getattr(obj, "complete", None))


def resolve_head(module) -> Callable[[], object]:
    """Devuelve una fábrica de cabezas a partir de un módulo.

    El arnés no le impone un nombre a la cabeza: le exige la interfaz
    `complete(messages) -> str`, que es la misma del modelo, y la busca en ese
    orden: una fábrica con nombre conocido, una clase que la cumpla, o la
    función suelta del módulo.
    """
    for name in FACTORY_NAMES:
        factory = getattr(module, name, None)
        if factory is None or isinstance(factory, type) or not callable(factory):
            continue
        candidate = factory()
        if _has_complete(candidate):
            return factory

    classes = [obj for obj in vars(module).values() if isinstance(obj, type) and _has_complete(obj)]
    own = [c for c in classes if getattr(c, "__module__", None) == getattr(module, "__name__", "")]
    ranked = own + [c for c in classes if c not in own]
    if ranked:
        return ranked[0]

    function = vars(module).get("complete")
    if callable(function) and not isinstance(function, type):
        class _Head:
            """La función suelta del módulo, con la forma que espera el sistema."""

            def complete(self, messages: list[dict]) -> str:
                return function(messages)

        return _Head

    raise TypeError(f"{module} no expone ninguna cabeza con complete(messages) -> str")


def forest_head() -> Callable[[], object]:
    """La cabeza del bosque, cargada de su módulo por la interfaz que cumple."""
    import importlib

    return resolve_head(importlib.import_module(FOREST_MODULE))


def stored_head() -> Callable[[], object]:
    """La cabeza que lee las clasificaciones guardadas, por la misma interfaz."""
    import importlib

    return resolve_head(importlib.import_module(CACHED_MODULE))


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _portable(path: Path) -> str:
    """La ruta tal y como puede publicarse: relativa, o sólo el nombre.

    El informe acaba en un repositorio público y no tiene por qué llevar
    dentro el directorio de nadie.
    """
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


def head_fingerprint(arm: str, head, *, deployment: str) -> dict:
    """Qué cabeza corrió, con lo que haga falta para saber si es la misma.

    Una cabeza que se lee de un fichero se identifica por el digest de ese
    fichero: si se reentrena a mitad de camino, las pasadas dejan de ser
    comparables y el informe tiene que poder decirlo.
    """
    if arm == "model":
        return {"arm": arm, "head": deployment}
    path = getattr(head, "path", None)
    if path is not None and Path(path).exists():
        return {
            "arm": arm,
            "head": _portable(Path(path)),
            "sha256": sha256_bytes(Path(path).read_bytes()),
        }
    return {"arm": arm, "head": type(head).__name__}


def head_factory(arm: str, *, deployment: str) -> Callable[[], object]:
    """La fábrica de cabezas de un brazo.

    El bosque se lee de disco una sola vez y se reutiliza: leerlo en cada
    llamada costaría más que clasificar. No lleva estado entre llamadas, así
    que compartirlo entre hilos no cambia lo que responde. Lo mismo vale para
    la cabeza que sirve las clasificaciones guardadas.
    """
    if arm == "model":
        return lambda: AzureModel(deployment=deployment)
    if arm == "rf":
        forest = forest_head()()
        return lambda: forest
    if arm == "cached":
        stored = stored_head()()
        return lambda: stored
    raise SystemExit(f"brazo desconocido: {arm}")


# --- línea de comandos --------------------------------------------------


def estimate(projects: int, passes: int, changing: int, repeats: int = REPEATS) -> dict:
    """Llamadas y coste del brazo del modelo, antes de gastar nada."""
    calls = projects * passes + changing * repeats
    cost = calls * (TOKENS_IN * PRICE_IN + TOKENS_OUT * PRICE_OUT) / 1_000_000
    return {"calls": calls, "usd": round(cost, 2)}


def _pass_path(runs: Path, arm: str, pass_id: str) -> Path:
    return runs / arm / f"{pass_id}.json"


def _load_passes(runs: Path, arm: str, pass_ids: Sequence[str]) -> list[ArmPass]:
    return [
        ArmPass.model_validate_json(_pass_path(runs, arm, pid).read_text(encoding="utf-8"))
        for pid in pass_ids
    ]


def _pass_ids(seeds: Sequence[int]) -> list[str]:
    return [f"pasada-{n}" for n in range(1, len(seeds) + 1)]


def _run(args: argparse.Namespace) -> None:
    seed = int(os.environ.get("PYTHONHASHSEED", "-1"))
    if seed != args.seed:
        raise SystemExit(f"PYTHONHASHSEED={seed!r} no coincide con --seed {args.seed}")
    result = run_pass(
        args.arm,
        args.pass_id,
        seed=args.seed,
        slugs=corpus_slugs(args.corpus),
        corpus=args.corpus,
        taxonomy_path=args.taxonomy,
        make_head=head_factory(args.arm, deployment=args.deployment),
        dest=args.work / f"{args.arm}-{args.pass_id}",
        workers=args.workers,
    )
    out = args.out or _pass_path(args.runs, args.arm, args.pass_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    failed = sum(1 for p in result.projects if p.failed)
    print(f"{args.arm} {args.pass_id} seed={args.seed} fallos={failed} -> {out}")


def pass_argv(args: argparse.Namespace, arm: str, pass_id: str, seed: int) -> list[str]:
    """Los argumentos con los que se lanza una pasada en su propio proceso.

    Las opciones generales van antes del subcomando, que es donde el parser las
    espera.
    """
    return [
        "--corpus", str(args.corpus), "--taxonomy", str(args.taxonomy),
        "--runs", str(args.runs), "--work", str(args.work),
        "--deployment", args.deployment, "--workers", str(args.workers),
        "pass", "--arm", arm, "--pass-id", pass_id, "--seed", str(seed),
    ]


def _spawn(args: argparse.Namespace, arm: str, pass_id: str, seed: int) -> None:
    """Lanza una pasada con su `PYTHONHASHSEED`, que sólo se fija al arrancar."""
    subprocess.run(
        [sys.executable, "-m", "btm.harness.guardian", *pass_argv(args, arm, pass_id, seed)],
        env={**os.environ, "PYTHONHASHSEED": str(seed)},
        check=True,
    )


def _certify_arm(args: argparse.Namespace, arm: str, slugs: list[str]) -> Certification:
    passes = _load_passes(args.runs, arm, _pass_ids(args.seeds))
    certification = certify(
        arm,
        head_factory(arm, deployment=args.deployment),
        frozen_contexts(passes, slugs),
        repeats=args.repeats,
        workers=args.workers,
    )
    path = args.runs / arm / "certificacion.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(certification.model_dump_json(indent=2), encoding="utf-8")
    return certification


def _changing_union(args: argparse.Namespace) -> list[str]:
    """Los proyectos que cambian de etiqueta en cualquiera de los brazos.

    Se certifican los mismos proyectos en los dos: el contexto congelado es el
    mismo, y así las dos fracciones se leen una contra la otra.
    """
    moved: set[str] = set()
    for arm in args.arms:
        moved |= set(changes(_load_passes(args.runs, arm, _pass_ids(args.seeds))).changing)
    return sorted(moved)


def _certify(args: argparse.Namespace) -> None:
    slugs = _changing_union(args)
    print(f"proyectos que cambian de etiqueta: {len(slugs)} -> {slugs}")
    for arm in args.arms:
        certification = _certify_arm(args, arm, slugs)
        print(f"  {arm}: {certification.reproduced}/{certification.total}")


def _report(args: argparse.Namespace) -> None:
    arms = {arm: _load_passes(args.runs, arm, _pass_ids(args.seeds)) for arm in args.arms}
    certifications = {}
    for arm in args.arms:
        path = args.runs / arm / "certificacion.json"
        if path.exists():
            certifications[arm] = Certification.model_validate_json(
                path.read_text(encoding="utf-8")
            )
    heads = [
        head_fingerprint(arm, head_factory(arm, deployment=args.deployment)(), deployment=args.deployment)
        for arm in args.arms
    ]
    report = build_report(
        arms,
        certifications,
        corpus=args.corpus,
        seeds=args.seeds,
        repeats=args.repeats,
        heads=heads,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for arm, block in report["arms"].items():
        counts = [p["count"] for p in block["per_pass"]]
        certification = block["certification"]
        line = f"{arm}: cambian {len(block['changing'])} | por pasada {counts}"
        if certification:
            line += f" | certificación {certification['reproduced']}/{certification['total']}"
        print(line)
    print(f"informe -> {args.out}")


def _all(args: argparse.Namespace) -> None:
    projects = len(corpus_slugs(args.corpus))
    guess = estimate(projects, len(args.seeds), changing=6, repeats=args.repeats)
    print(
        f"{projects} proyectos x {len(args.seeds)} pasadas x {len(args.arms)} brazos | "
        f"brazo del modelo ~{guess['calls']} llamadas ~{guess['usd']} USD"
    )
    for arm in args.arms:
        for pass_id, seed in zip(_pass_ids(args.seeds), args.seeds):
            _spawn(args, arm, pass_id, seed)
    _certify(args)
    _report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btm-guardian")
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--runs", type=Path, default=Path("results/guardian"))
    parser.add_argument("--work", type=Path, default=Path(".work/guardian"))
    parser.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--arms", nargs="+", default=list(ARMS))
    sub = parser.add_subparsers(dest="stage", required=True)

    one = sub.add_parser("pass")
    one.add_argument("--arm", choices=HEADS, required=True)
    one.add_argument("--pass-id", dest="pass_id", required=True)
    one.add_argument("--seed", type=int, required=True)
    one.add_argument("--out", type=Path)
    one.set_defaults(fn=_run)

    certification = sub.add_parser("certify")
    certification.set_defaults(fn=_certify)

    report = sub.add_parser("report")
    report.add_argument("--out", type=Path, default=Path("results/guardian.json"))
    report.set_defaults(fn=_report)

    every = sub.add_parser("all")
    every.add_argument("--out", type=Path, default=Path("results/guardian.json"))
    every.set_defaults(fn=_all)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
