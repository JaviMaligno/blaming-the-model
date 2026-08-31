"""Armado de los dos paquetes de la segunda vuelta del control, y su congelación.

Esto es arnés: nunca se entrega, y lo que sale de aquí sí.

La primera vuelta (`btm.harness.guardian_case`) comparaba dos cabezas sobre el
mismo fallo y dejaba dos diferencias entre brazos que no eran la cabeza:

- **La frase de estabilidad no daba lo mismo.** 260/260 el bosque y 240/260 el
  modelo. El bosque se lee «perfectamente determinista» y el modelo no, así que
  el argumento para descartar la cabeza sólo estaba disponible de verdad en un
  brazo — y ese argumento es justo lo que predice que se mire aguas arriba.
- **El árbol entregado del brazo del modelo llevaba dentro la llamada al
  servicio.** Un culpable legítimo que el otro brazo no tenía.

Las dos se cierran con la misma pieza: el sistema guarda la clasificación de
cada contexto y la sirve de ahí. Con eso el brazo del modelo es
demostrablemente reproducible y certifica lo mismo que el bosque, y su cabeza
lee de un fichero igual que el bosque lee el suyo. El fallo no se toca: sigue
aguas arriba de lo guardado, y como el contexto cambia de una pasada a otra,
guardar no lo tapa.

De ahí lo que gobierna este módulo, además de lo que hereda de
`btm.harness.guardian_case`:

- **Los dos encargos se separan en una sola línea**, la que dice quién decide.
  Todo lo demás es el mismo texto: la frase de estabilidad con el mismo número
  en los dos, y la frase que dice que el sistema reutiliza lo ya clasificado,
  también con las mismas palabras en los dos. Que sea una línea no se confía a
  la redacción: `brief_diff` lo comprueba y se planta si no lo es.
- **Los dos paquetes van sin árbol.** Ésa es la condición que porta el
  contraste, y sin árbol la segunda asimetría no puede reaparecer por detrás.

    python -m btm.harness.guardian_case_v2 --cases <dir>
"""

import argparse
import difflib
import shutil
from pathlib import Path

import json

from btm.harness.a5_case import audited, flatten_clock, freeze, pass_table
from btm.harness.guardian import ArmPass, Certification
from btm.harness.guardian_case import HEAD_SENTENCE, anonymous, audit_package

VARIANT = "A1"

# El brazo del paquete y el brazo del arnés no se llaman igual: el paquete no
# dice «model» por ningún sitio, porque decirlo sería nombrar la mitad de la
# respuesta en uno de los dos lados. El brazo del modelo se sirve de lo
# guardado, que es lo que lo deja tan reproducible como el bosque.
ARMS = ("llm", "rf")
HARNESS_ARM = {"llm": "cached", "rf": "rf"}

CASES: dict[str, str] = {"v2-llm": "llm", "v2-rf": "rf"}

# Lo que el sistema hace con cada clasificación, dicho igual en los dos brazos.
# Es información honesta sobre el sistema, no una pista: va en los dos o no va.
STORE_SENTENCE = (
    "El sistema guarda la respuesta de cada clasificación y la reutiliza si vuelve a\n"
    "ver el mismo contexto."
)

BRIEF = """# Encargo

El clasificador asigna a cada proyecto de software un código de una taxonomía de
dominio de aplicación, junto con una confianza y una justificación. Se ejecuta
todas las noches sobre el catálogo entero, {n} proyectos, en una sola pasada.

{head}

{store}

El resultado no es siempre el mismo. Comparando las últimas {p} pasadas, unos
pocos proyectos aparecen con un código distinto de una noche a otra; el resto no
se mueve. Cuáles son esos proyectos tampoco es siempre igual.

Cuando cogemos uno de los proyectos afectados y lo volvemos a clasificar por
separado, sale bien: la etiqueta que esperábamos, y la misma todas las veces.

Re-ejecutar la clasificación sobre el mismo contexto reprodujo la salida en
{reproduced} de {total} casos.

En `pasadas.md` está el código asignado a cada proyecto en cada pasada, y en
`runs/` el registro de cada corrida. En `corpus/` están los documentos con los
que trabajó.

Investiga a qué se debe y qué harías al respecto. Puedes pedir lo que te falte.
"""


def brief(n: int, p: int, *, arm: str, reproduced: int, total: int) -> str:
    """El encargo de un brazo: el mismo texto, con su cabeza."""
    return BRIEF.format(
        n=n,
        p=p,
        head=HEAD_SENTENCE[arm],
        store=STORE_SENTENCE,
        reproduced=reproduced,
        total=total,
    )


def _changed(diff: str, sign: str) -> list[str]:
    """Las líneas que el diff marca como quitadas o puestas."""
    return [line[1:] for line in diff.splitlines() if line[:1] == sign and line[1:2] != sign]


def brief_diff(first: str, second: str) -> str:
    """El diff entre los dos encargos, comprobando que es una sola línea.

    La comprobación va aquí y no sólo en el test porque es la condición que
    sostiene la lectura: si los encargos se separan en algo más que en quién
    decide, lo que se mida después no es lo que se quería medir.
    """
    diff = "".join(
        difflib.unified_diff(
            first.splitlines(keepends=True),
            second.splitlines(keepends=True),
            fromfile="v2-llm/BRIEF.md",
            tofile="v2-rf/BRIEF.md",
            n=1,
        )
    )
    removed, added = _changed(diff, "-"), _changed(diff, "+")
    esperado = ([HEAD_SENTENCE["llm"]], [HEAD_SENTENCE["rf"]])
    if (removed, added) != esperado:
        raise SystemExit(
            "los dos encargos se separan en algo más que en quién decide:\n" + diff
        )
    return diff


# --- el paquete ---------------------------------------------------------


def build_case(
    passes: list[ArmPass],
    corpus: Path,
    out: Path,
    *,
    arm: str,
    certification: Certification,
) -> Path:
    """Escribe el paquete de un brazo: encargo, tabla, registros y corpus."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    projects = sorted({p.slug for result in passes for p in result.projects})
    (out / "BRIEF.md").write_text(
        brief(
            len(projects),
            len(passes),
            arm=arm,
            reproduced=certification.reproduced,
            total=certification.total,
        ),
        encoding="utf-8",
    )
    (out / "pasadas.md").write_text(pass_table(passes), encoding="utf-8")

    for result in passes:
        target = out / "runs" / result.pass_id
        target.mkdir(parents=True, exist_ok=True)
        # Por slug, no por posición: el nombre del fichero no dice cuándo se
        # atendió a cada proyecto.
        for project in sorted(result.projects, key=lambda p: p.slug):
            (target / f"{project.slug}.jsonl").write_text(
                anonymous(project.trace_jsonl), encoding="utf-8"
            )

    shutil.copytree(
        corpus, out / "corpus", ignore=shutil.ignore_patterns("__pycache__", "README.md")
    )

    flatten_clock(out)
    return out


def check_symmetry(certifications: dict[str, Certification]) -> None:
    """Se planta si las dos cabezas no certifican el mismo número.

    Dos números distintos reabren el defecto que esta vuelta viene a cerrar, y
    lo reabren en silencio: el encargo seguiría pareciendo el mismo.
    """
    numbers = {(c.reproduced, c.total) for c in certifications.values()}
    if len(numbers) > 1:
        raise SystemExit(f"las cabezas no certifican lo mismo: {sorted(numbers)}")


def build_all(
    arms: dict[str, list[ArmPass]],
    corpus: Path,
    out_dir: Path,
    *,
    certifications: dict[str, Certification],
) -> dict[str, Path]:
    """Los dos paquetes, sin árbol, para los dos brazos."""
    check_symmetry(certifications)
    return {
        name: build_case(
            arms[arm],
            corpus,
            out_dir / name,
            arm=arm,
            certification=certifications[arm],
        )
        for name, arm in CASES.items()
    }


# --- línea de comandos --------------------------------------------------


def _pass_ids(runs: Path, harness_arm: str) -> list[str]:
    return sorted(p.stem for p in (runs / harness_arm).glob("pasada-*.json"))


def load_arm(runs: Path, arm: str) -> list[ArmPass]:
    """Las pasadas de un brazo, en el orden en que se corrieron."""
    harness = HARNESS_ARM[arm]
    return [
        ArmPass.model_validate_json((runs / harness / f"{pid}.json").read_text(encoding="utf-8"))
        for pid in _pass_ids(runs, harness)
    ]


def load_certification(runs: Path, arm: str) -> Certification:
    path = runs / HARNESS_ARM[arm] / "certificacion.json"
    return Certification.model_validate_json(path.read_text(encoding="utf-8"))


def _report(args: argparse.Namespace) -> None:
    arms = {arm: load_arm(args.runs, arm) for arm in ARMS}
    certifications = {arm: load_certification(args.runs, arm) for arm in ARMS}
    for arm in ARMS:
        c = certifications[arm]
        print(f"{arm} ({HARNESS_ARM[arm]}): certificación {c.reproduced}/{c.total}")

    cases = build_all(arms, args.corpus, args.cases, certifications=certifications)

    offences = {name: audit_package(path) for name, path in cases.items()}
    for name, found in offences.items():
        print(f"{name}: {len(audited(cases[name]))} ficheros auditados, {len(found)} hallazgos")
        for relative, word in found:
            print(f"    {relative}: {word!r}")

    diff = brief_diff(
        (cases["v2-llm"] / "BRIEF.md").read_text(encoding="utf-8"),
        (cases["v2-rf"] / "BRIEF.md").read_text(encoding="utf-8"),
    )
    print("\ndiff de los dos encargos:\n" + diff)

    args.frozen.parent.mkdir(parents=True, exist_ok=True)
    args.frozen.write_text(
        json.dumps(freeze(cases), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"congelado -> {args.frozen}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btm-guardian-case-v2")
    parser.add_argument("--runs", type=Path, default=Path("results/guardian"))
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, default=Path("results/frozen-guardian-v2.json"))
    parser.set_defaults(fn=_report)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
