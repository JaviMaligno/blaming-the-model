"""El corpus sobre el que corre el escenario A5, y su cribado.

Esto es arnés: nunca se entrega. Lo que se entrega son los snapshots que salen
de aquí, y ésos no pueden confesar nada.

El corpus es captura corriente y nada más: mismas reglas que `data/corpus/`,
URLs con owner, cero datos inventados. Lo que lo distingue es a quién mete
dentro y a quién deja fuera:

- Incluye cuatro pares de proyectos homónimos —dos repositorios distintos que
  se llaman igual—. Sus snapshots no comparten ni una URL; lo único que
  comparten es el nombre corto y la numeración de sus secciones, que es lo que
  el paquete usa para indexar las páginas leídas. La coincidencia no está
  escrita en ningún fichero: es una propiedad de dos ficheros leídos a la vez, y
  sólo importa por cómo el código de arriba construye su clave. `audit()`
  comprueba las dos mitades: que ninguna URL se repita entre proyectos
  distintos, y que los únicos nombres repetidos sean los cuatro buscados.
- Cada repositorio de relleno se clasifica varias veces con el sistema sano y
  se descarta si no responde siempre lo mismo. Sin ese cribado, un repositorio
  que oscila por su cuenta se confunde con uno contaminado, y el hecho del que
  cuelga la medición —«todo cambio de etiqueta observado es una corrida
  contaminada»— deja de ser un hecho.

Los cuatro pares salen de la Fase 0 (`results/fase0-pares.json`): 514
clasificaciones reales para comprobar que ambos miembros son estables en
solitario y que el segundo cambia de etiqueta al servírsele la documentación
del primero.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

from btm.harness.ingest import capture, write
from btm.harness.model import AzureModel
from btm.system.classifier import classify
from btm.system.corpus import Document, RepoSnapshot, load_all
from btm.system.taxonomy import Taxonomy
from btm.variants.A5.pages import section_of

# Con menos páginas en común el par no da para sembrar la caché: el documento
# ajeno tiene que poder entrar en la ventana de contexto de la víctima.
MIN_SHARED_PAGES = 3

# Repositorios que responden distinto de una corrida sana a otra, y que por eso
# no pueden estar en el corpus: un cambio de etiqueta suyo se confundiría con
# uno provocado. Los tres primeros los condenó el gate de calibración
# (`results/gate.json`); los cuatro siguientes, el cribado de este corpus
# (`results/scenario-cribado.json`).
UNSTABLE = (
    "harumiWeb--xlflow",
    "jacovinus--snoutdb",
    "Radiergummi--cetacean",
    "Alexli18--binex",
    "jeyben--fixedformat4j",
    "josephleblanc--ploke",
    "vector-index-bench--vibe",
)


class Pair(NamedTuple):
    """Dos proyectos distintos que se llaman igual.

    `donor` es el que siembra la caché y `victim` el que recibe sus páginas;
    el reparto lo decidió la Fase 0 midiendo en qué dirección cambia la
    etiqueta.
    """

    name: str
    donor: str
    victim: str


PAIRS = (
    Pair("orion", donor="pinterest--orion", victim="orion-rs--orion"),
    Pair("badger", donor="outcaste-io--badger", victim="badger-cash--badger"),
    Pair("atlas", donor="karam-ajaj--atlas", victim="dawarich-app--atlas"),
    Pair("sentry", donor="jasonrichardsmith--sentry", victim="samueleaton--sentry"),
    Pair("otter", donor="AmadeusITGroup--otter", victim="rackerlabs--otter"),
    Pair("relay", donor="getsentry--relay", victim="puppetlabs--relay"),
    Pair("phoenix", donor="ACINQ--phoenix", victim="fabiospampinato--phoenix"),
)


class Audit(BaseModel):
    """El corpus cruzado consigo mismo, por URL y por clave de página."""

    shared_within_pair: dict[str, int]
    stray: dict[str, list[str]]
    missing: list[str]
    shared_urls: dict[str, list[str]]

    @property
    def ok(self) -> bool:
        return (
            not self.missing
            and not self.stray
            and not self.shared_urls
            and all(n >= MIN_SHARED_PAGES for n in self.shared_within_pair.values())
        )


def page_key(snapshot: RepoSnapshot, document: Document) -> str:
    """Con qué se identifica una página en el índice que usa el paquete.

    Nombre del proyecto y sección, tal y como los compone `section_of` en el
    módulo entregado: se importa de allí para que esta comprobación siga a la
    clave de verdad en vez de a una copia suya. Para una sección de README la
    sección es el número del fragmento, que dos homónimos numeran igual; para
    un documento sin fragmento es la url entera, que lleva owner y por tanto
    no la comparte nadie.
    """
    return f"{snapshot.name}#{section_of(document.url)}"


def url_collisions(snapshots: list[RepoSnapshot]) -> dict[str, list[str]]:
    """Las URLs que publica más de un repositorio, con quiénes las publican."""
    owners: dict[str, set[str]] = {}
    for snapshot in snapshots:
        for document in snapshot.documents:
            owners.setdefault(document.url, set()).add(snapshot.slug)
    return {url: sorted(slugs) for url, slugs in sorted(owners.items()) if len(slugs) > 1}


def key_collisions(snapshots: list[RepoSnapshot]) -> dict[str, list[str]]:
    """Las claves de página que produce más de un repositorio."""
    owners: dict[str, set[str]] = {}
    for snapshot in snapshots:
        for document in snapshot.documents:
            owners.setdefault(page_key(snapshot, document), set()).add(snapshot.slug)
    return {key: sorted(slugs) for key, slugs in sorted(owners.items()) if len(slugs) > 1}


def audit(snapshots: list[RepoSnapshot], pairs: list[Pair] | tuple[Pair, ...]) -> Audit:
    """Comprueba que coincide lo que tiene que coincidir, y sólo eso."""
    present = {s.slug for s in snapshots}
    missing = [slug for pair in pairs for slug in (pair.donor, pair.victim) if slug not in present]

    declared = {frozenset((pair.donor, pair.victim)): pair.name for pair in pairs}
    shared = dict.fromkeys((pair.name for pair in pairs), 0)
    stray: dict[str, list[str]] = {}
    for key, slugs in key_collisions(snapshots).items():
        name = declared.get(frozenset(slugs))
        if name is None:
            stray[key] = slugs
        else:
            shared[name] += 1
    return Audit(
        shared_within_pair=shared,
        stray=stray,
        missing=missing,
        shared_urls=url_collisions(snapshots),
    )


class Screening(BaseModel):
    """Lo que respondió el sistema sano sobre un repositorio, corrida a corrida."""

    slug: str
    codes: list[str]

    @property
    def stable(self) -> bool:
        return len(set(self.codes)) == 1


def screen(snapshot: RepoSnapshot, taxonomy: Taxonomy, deployment: str, runs: int) -> Screening:
    """Clasifica un repositorio varias veces con el sistema sano."""
    codes = []
    for i in range(runs):
        classification, _ = classify(
            snapshot, taxonomy, AzureModel(deployment=deployment), run_id=f"s{i}"
        )
        codes.append(classification.code)
    return Screening(slug=snapshot.slug, codes=codes)


def filler_slugs(corpus_root: Path) -> list[str]:
    """Los repositorios de relleno candidatos, sin los que ya se sabe que oscilan."""
    return sorted(
        p.name
        for p in corpus_root.iterdir()
        if (p / "snapshot.json").exists() and p.name not in UNSTABLE
    )


def _described(slug: str, roots: list[Path]) -> bool:
    """¿Traía descripción la captura anterior de este repositorio?

    El criterio del corpus pide repositorios con descripción y sin ella en
    proporción parecida, y para conseguirlo parte de las capturas se hicieron
    con `keep_description=False`. Recapturar sin heredar esa decisión
    devolvería la descripción a la mitad del corpus y cambiaría el plan de
    consultas del clasificador, que pregunta de más cuando no la hay.
    """
    for root in roots:
        path = root / slug / "snapshot.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["description"] is not None
    return True


def _capture(args: argparse.Namespace) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    # La captura anterior manda sobre la decisión de la descripción; con el
    # destino vacío, la heredan los corpus de los que salió cada repositorio.
    roots = [args.out, args.pairs, args.corpus]
    members = [slug for pair in PAIRS for slug in (pair.donor, pair.victim)]
    targets = members + filler_slugs(args.corpus)[: args.filler]

    def one(slug: str) -> tuple[str, dict | None]:
        return slug, capture(
            slug.replace("--", "/", 1), keep_description=_described(slug, roots)
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, targets))

    for slug, snapshot in results:
        if snapshot is None:
            print(f"  sin captura: {slug}")
            continue
        write(snapshot, args.out)
    print(f"{sum(s is not None for _, s in results)}/{len(targets)} snapshots en {args.out}")


def _audit(args: argparse.Namespace) -> None:
    report = audit(load_all(args.out), PAIRS)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    print("OK" if report.ok else "NO PASA")


def _screen(args: argparse.Namespace) -> None:
    taxonomy = Taxonomy.load(args.taxonomy)
    members = {slug for pair in PAIRS for slug in (pair.donor, pair.victim)}
    snapshots = [s for s in load_all(args.out) if s.slug not in members]
    if args.only:
        snapshots = [s for s in snapshots if s.slug in set(args.only)]
    print(f"{len(snapshots)} repositorios de relleno × {args.runs} corridas sanas "
          f"con {args.deployment}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(lambda s: screen(s, taxonomy, args.deployment, args.runs), snapshots)
        )

    payload = [{"slug": r.slug, "codes": r.codes, "stable": r.stable} for r in results]
    if args.only and args.report.exists():
        # Recribado parcial: se reemplazan sólo las entradas pedidas.
        previous = json.loads(args.report.read_text(encoding="utf-8"))
        refreshed = {entry["slug"] for entry in payload}
        payload = sorted(
            [e for e in previous if e["slug"] not in refreshed] + payload,
            key=lambda e: e["slug"],
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in sorted(results, key=lambda r: (r.stable, r.slug)):
        print(f"{r.slug[:46]:46} {'estable' if r.stable else 'OSCILA '} {sorted(set(r.codes))}")
    print(f"\n{sum(r.stable for r in results)}/{len(results)} estables. Detalle en {args.report}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-scenario-corpus")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--pairs", type=Path, default=Path("data/pairs"))
    parser.add_argument("--out", type=Path, default=Path("data/scenario"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--report", type=Path, default=Path("results/scenario-cribado.json"))
    parser.add_argument("--filler", type=int, default=43)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", nargs="*", default=None,
                        help="cribar sólo estos slugs, conservando el resto del informe")
    parser.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    parser.add_argument("stage", choices=("capture", "audit", "screen"))
    args = parser.parse_args()
    {"capture": _capture, "audit": _audit, "screen": _screen}[args.stage](args)


if __name__ == "__main__":
    main()
