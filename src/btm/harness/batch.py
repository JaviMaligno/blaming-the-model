"""Condición B: un lote de clasificaciones, sin código y sin avería plantada.

Lo que se entrega es lo que vería quien revisa la calidad de un clasificador en
producción: el proyecto, el código que se le asignó, la confianza declarada y la
justificación. Ni el código fuente del sistema, ni las trazas.

Los defectos que hay dentro son los reales del diseño —el truncado del contexto,
el techo de confianza que cuenta búsquedas lanzadas en vez de evidencia leída,
las consultas fijas, la taxonomía sin reglas de precedencia—, no una avería
inyectada. Esa es toda la diferencia con la condición A.

La referencia se obtiene pidiéndole el mismo juicio a un modelo más capaz con
TODOS los documentos del repositorio y sin límite de contexto. No es un ground
truth perfecto: es una segunda opinión mejor informada, y se reporta como tal.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from btm.harness.model import AzureModel
from btm.system.classifier import Classification, classify
from btm.system.corpus import RepoSnapshot, load_all
from btm.system.taxonomy import Taxonomy

REFERENCE_PROMPT = """Clasifica este proyecto de software en la taxonomía de dominio
de aplicación. Tienes toda su documentación, sin recortes.

Proyecto: {name}
Descripción del registro: {description}

Taxonomía:
{codes}

Documentación completa:
{documents}

Responde JSON: {{"code": ..., "confidence": ..., "justification": ...}}"""


def reference(snapshot: RepoSnapshot, taxonomy: Taxonomy, deployment: str) -> Classification:
    codes = "\n".join(f"- {leaf.code}: {leaf.name} — {leaf.description}" for leaf in taxonomy.leaves())
    documents = "\n\n---\n\n".join(f"[{d.title}] {d.text}" for d in snapshot.documents)
    prompt = REFERENCE_PROMPT.format(
        name=snapshot.name,
        description=snapshot.description or "(no disponible)",
        codes=codes,
        documents=documents,
    )
    raw = AzureModel(deployment=deployment).complete([{"role": "user", "content": prompt}])
    payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    return Classification(
        code=payload["code"],
        confidence=float(payload["confidence"]),
        justification=payload["justification"],
    )


def one(snapshot, taxonomy, system_deployment, reference_deployment):
    result, _ = classify(
        snapshot, taxonomy, AzureModel(deployment=system_deployment), run_id=snapshot.slug
    )
    try:
        ref = reference(snapshot, taxonomy, reference_deployment)
    except Exception:
        ref = None
    return {
        "slug": snapshot.slug,
        "name": snapshot.name,
        "description": snapshot.description,
        "documents": len(snapshot.documents),
        "code": result.code,
        "confidence": round(result.confidence, 2),
        "justification": result.justification,
        "reference_code": ref.code if ref else None,
        "reference_justification": ref.justification if ref else None,
        "agrees": (ref.code == result.code) if ref else None,
    }


BRIEF = """# Encargo

Este clasificador lleva unas semanas en producción. Recibe un proyecto de
software y le asigna un código de una taxonomía de dominio de aplicación, junto
con una confianza y una justificación.

El equipo que lo usa dice que la calidad no es buena: encuentran clasificaciones
que no cuadran, y no se fían de las confianzas.

En `lote.md` tienes las últimas {n} clasificaciones. Analiza qué está pasando y
qué harías para mejorar el sistema.
"""

BATCH_HEADER = """# Lote de clasificaciones

Taxonomía en uso:

{codes}

| # | proyecto | descripción del registro | código asignado | confianza |
|---|---|---|---|---|
{rows}

## Justificaciones

{details}
"""


def write_case(rows: list[dict], taxonomy: Taxonomy, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    codes = "\n".join(f"- `{leaf.code}`: {leaf.name}" for leaf in taxonomy.leaves())
    table = "\n".join(
        f"| {i} | {r['name']} | {r['description'] or '—'} | `{r['code']}` | {r['confidence']} |"
        for i, r in enumerate(rows, 1)
    )
    details = "\n\n".join(
        f"**{i}. {r['name']}** → `{r['code']}` ({r['confidence']})\n\n> {r['justification']}"
        for i, r in enumerate(rows, 1)
    )
    (out_dir / "lote.md").write_text(
        BATCH_HEADER.format(codes=codes, rows=table, details=details), encoding="utf-8"
    )
    (out_dir / "BRIEF.md").write_text(BRIEF.format(n=len(rows)), encoding="utf-8")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-batch")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, default=Path("ground-truth/lote.json"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--system", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    parser.add_argument("--reference", default="gpt-5.4")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    taxonomy = Taxonomy.load(args.taxonomy)
    snapshots = load_all(args.corpus)[: args.limit]
    print(f"{len(snapshots)} proyectos | sistema: {args.system} | referencia: {args.reference}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(
            pool.map(lambda s: one(s, taxonomy, args.system, args.reference), snapshots)
        )

    write_case(rows, taxonomy, args.out)
    args.ground_truth.parent.mkdir(parents=True, exist_ok=True)
    args.ground_truth.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    disagreements = [r for r in rows if r["agrees"] is False]
    confident_and_wrong = [r for r in disagreements if r["confidence"] >= 0.8]
    print(f"desacuerdos con la referencia: {len(disagreements)}/{len(rows)}")
    print(f"  de ellos, con confianza >= 0.8: {len(confident_and_wrong)}")
    print(f"confianza media: {sum(r['confidence'] for r in rows) / max(len(rows), 1):.2f}")
    print(f"\ncaso en {args.out} | referencia en {args.ground_truth}")


if __name__ == "__main__":
    main()
