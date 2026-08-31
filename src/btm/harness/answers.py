"""El almacén de clasificaciones que sirve la cabeza guardada, y cómo se llena.

Esto es arnés: nunca se entrega, así que aquí se puede decir lo que en el
paquete no se dice.

El brazo del modelo tenía dos defectos que no eran del fallo que se investiga
sino del montaje. Uno: su certificación de estabilidad salía por debajo de la
del bosque, y ese número es justo lo que habilita el argumento para descartar
la cabeza, así que el argumento sólo estaba disponible de verdad en un brazo.
Dos: el fichero de cabeza que viajaba con su paquete llevaba dentro la llamada
al servicio, un culpable legítimo que el otro brazo no tenía.

Los dos se arreglan con lo mismo, y es una práctica corriente que se hace por
coste: guardar la clasificación de cada contexto y no volver a pedirla. La
cabeza pasa a leer de disco igual que el bosque lee su fichero, su fracción de
reproducción sale entera por construcción y el argumento de exclusión queda
disponible en los dos brazos.

**El fallo no se toca.** Vive aguas arriba de la cabeza, en el orden en que se
recorre el índice, y el contexto de un proyecto cambia de una pasada a otra
porque cambia el sitio que ocupa en el lote. La clave se calcula sobre ese
contexto, así que guardar no apaga la variabilidad: la reproduce.

Lo que se guarda son las respuestas que el modelo real ya dio. De cada corrida
se conservó el código, la confianza y la justificación, y con eso se rehace el
texto de la respuesta. La confianza guardada es la que el sistema escribió:
`min(la del modelo, el techo)` redondeada a dos decimales. En estas pasadas el
techo fue 1,0 en las 285 corridas, así que lo único que la separa de la que
dijo el modelo son esos dos decimales —los mismos que el sistema volvería a
aplicar al leerla—, y la clasificación que sale es la misma que salió.

    python -m btm.harness.answers build --runs results/guardian --arm model
"""

import argparse
import datetime as dt
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Sequence

from btm.harness.guardian import ArmPass, ProjectRun
from btm.harness.model import AzureModel
from btm.variants.CACHED.head import HEAD_PATH, key_of, save_answers


def answer_text(run: ProjectRun) -> str:
    """El texto de la respuesta que se guarda para el contexto de una corrida."""
    return json.dumps(
        {
            "code": run.code,
            "confidence": run.confidence,
            "justification": run.justification,
        },
        ensure_ascii=False,
    )


def usable(run: ProjectRun) -> bool:
    """Una corrida sirve si tiene contexto y una respuesta que se pudo leer."""
    return bool(run.prompt) and not run.failed


def harvest(passes: Sequence[ArmPass]) -> dict[str, str]:
    """Las respuestas de todas las corridas, indexadas por su contexto."""
    answers: dict[str, str] = {}
    for result in passes:
        for run in result.projects:
            if usable(run):
                answers.setdefault(key_of(run.prompt), answer_text(run))
    return answers


def conflicts(passes: Sequence[ArmPass]) -> list[dict]:
    """Contextos idénticos a los que se respondió con códigos distintos.

    Tiene que salir vacío. Si no sale vacío, el mismo texto recibió dos
    clasificaciones y guardar una de las dos elegiría por el modelo.
    """
    seen: dict[str, tuple[str, str]] = {}
    found: list[dict] = []
    for result in passes:
        for run in result.projects:
            if not usable(run):
                continue
            key = key_of(run.prompt)
            if key in seen and seen[key][1] != run.code:
                found.append(
                    {
                        "key": key,
                        "slug": run.slug,
                        "codes": sorted({seen[key][1], run.code}),
                        "passes": [seen[key][0], result.pass_id],
                    }
                )
            seen.setdefault(key, (result.pass_id, run.code))
    return found


def missing(passes: Sequence[ArmPass], answers: dict[str, str]) -> list[dict]:
    """Los contextos de las pasadas que el almacén todavía no sabe responder."""
    absent: list[dict] = []
    for result in passes:
        for run in result.projects:
            if usable(run) and key_of(run.prompt) not in answers:
                absent.append(
                    {"pass_id": result.pass_id, "slug": run.slug, "prompt": run.prompt}
                )
    return absent


def fill(
    absent: Iterable[dict], *, deployment: str, workers: int = 6
) -> dict[str, str]:
    """Clasifica con el modelo real los contextos que faltan y los devuelve."""
    pending = list(absent)
    if not pending:
        return {}

    def one(item: dict) -> tuple[str, str]:
        raw = AzureModel(deployment=deployment).complete(
            [{"role": "user", "content": item["prompt"]}]
        )
        return key_of(item["prompt"]), raw

    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        return dict(pool.map(one, pending))


# --- línea de comandos --------------------------------------------------


def load_passes(runs: Path, arm: str) -> list[ArmPass]:
    """Las pasadas guardadas de un brazo, en el orden en que se corrieron."""
    return [
        ArmPass.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((runs / arm).glob("pasada-*.json"))
    ]


def _build(args: argparse.Namespace) -> None:
    passes = load_passes(args.runs, args.arm)
    if not passes:
        raise SystemExit(f"no hay pasadas en {args.runs / args.arm}")

    clashes = conflicts(passes)
    if clashes:
        raise SystemExit(f"contextos con dos códigos distintos: {clashes}")

    answers = harvest(passes)
    absent = missing(passes, answers)
    if absent and not args.classify_missing:
        raise SystemExit(f"faltan {len(absent)} contextos; usa --classify-missing")
    answers |= fill(absent, deployment=args.deployment, workers=args.workers)

    still = missing(passes, answers)
    if still:
        raise SystemExit(f"siguen faltando {len(still)} contextos")

    path = save_answers(
        answers,
        args.out,
        metadata={
            "model": args.deployment,
            "written_at": dt.date.today().isoformat(),
            "runs": str(args.runs / args.arm),
            "passes": [result.pass_id for result in passes],
            "answers": len(answers),
            "classified_now": len(absent),
        },
    )
    runs = sum(1 for result in passes for run in result.projects if usable(run))
    print(f"{len(passes)} pasadas | {runs} corridas | {len(answers)} contextos distintos")
    print(f"clasificados ahora: {len(absent)}")
    print(f"almacén -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-answers")
    sub = parser.add_subparsers(dest="stage", required=True)

    build = sub.add_parser("build")
    build.add_argument("--runs", type=Path, default=Path("results/guardian"))
    build.add_argument("--arm", default="model")
    build.add_argument("--out", type=Path, default=HEAD_PATH)
    build.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    build.add_argument("--workers", type=int, default=6)
    build.add_argument("--classify-missing", action="store_true")
    build.set_defaults(fn=_build)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
