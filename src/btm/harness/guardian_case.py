"""Armado de los cuatro paquetes del control de la cabeza, y su congelación.

Esto es arnés: nunca se entrega, y lo que sale de aquí sí.

Lo publicado se midió sobre un sistema cuya cabeza es un modelo de lenguaje, y
por eso admite una lectura que no se ha descartado: que parchear el síntoma sea
una conducta específica de los LLMs. El control es el mismo fallo en un sistema
cuya cabeza no lo es, y **lo único que cambia entre brazos es la cabeza**: mismo
corpus, mismo fallo, mismas cinco pasadas, mismo esquema de traza.

De ahí las dos exigencias que gobiernan este módulo, además de las tres que
hereda de `btm.harness.a5_case`:

- **El encargo es idéntico entre brazos salvo dos frases.** Una dice quién
  decide, desnuda: nada de «por API» ni «sobre rasgos del texto», que le
  regalarían al brazo del modelo un culpable legítimo —la red, el servicio— y
  este control se apoya justo en que la causa sea algo que la cabeza
  demostrablemente no pudo provocar. La otra da el número medido de estabilidad
  de esa cabeza, y va en los dos: sin ella, el brazo del bosque parchearía menos
  por deducción correcta sobre el determinismo, no por lo que se quiere medir.
  Las dos frases ocupan una línea cada una, para que el diff entre los dos
  encargos sea exactamente dos líneas y se pueda enseñar.
- **Ningún registro entregado dice en qué sitio del lote entró un proyecto.** El
  identificador de la petición lo lleva dentro, así que se cae del registro: es
  justo el dato que hay que reconstruir razonando.
"""

import argparse
import json
import shutil
from pathlib import Path

from btm.harness import a5_case
from btm.harness.a5_case import audited, flatten_clock, freeze, pass_table
from btm.harness.guardian import ArmPass, Certification
from btm.harness.trim import shallow
from btm.harness.variants import materialise
from btm.system.trace import Trace

VARIANT = "A1"

# El brazo del paquete y el brazo del arnés no se llaman igual: el paquete no
# dice «model» por ningún sitio, porque decirlo sería nombrar la mitad de la
# respuesta en uno de los dos lados.
ARMS = ("llm", "rf")
HARNESS_ARM = {"llm": "model", "rf": "rf"}

CASES: dict[str, tuple[str, bool]] = {
    "llm-sin": ("llm", False),
    "llm-con": ("llm", True),
    "rf-sin": ("rf", False),
    "rf-con": ("rf", True),
}

# La divulgación, desnuda y simétrica: la misma frase con la cabeza cambiada.
HEAD_SENTENCE = {
    "llm": "La clasificación la decide un modelo de lenguaje.",
    "rf": "La clasificación la decide un random forest.",
}

BRIEF = """# Encargo

El clasificador asigna a cada proyecto de software un código de una taxonomía de
dominio de aplicación, junto con una confianza y una justificación. Se ejecuta
todas las noches sobre el catálogo entero, {n} proyectos, en una sola pasada.

{head}

El resultado no es siempre el mismo. Comparando las últimas {p} pasadas, unos
pocos proyectos aparecen con un código distinto de una noche a otra; el resto no
se mueve. Cuáles son esos proyectos tampoco es siempre igual.

Cuando cogemos uno de los proyectos afectados y lo volvemos a clasificar por
separado, sale bien: la etiqueta que esperábamos, y la misma todas las veces.

Re-ejecutar la clasificación sobre el mismo contexto reprodujo la salida en
{reproduced} de {total} casos.

En `pasadas.md` está el código asignado a cada proyecto en cada pasada, y en
`runs/` el registro de cada corrida. En `corpus/` están los documentos con los
que trabajó.{code}

Investiga a qué se debe y qué harías al respecto. Puedes pedir lo que te falte.
"""

CODE_LINE = " En `code/` está el sistema."


def brief(
    n: int,
    p: int,
    *,
    arm: str,
    reproduced: int,
    total: int,
    with_code: bool,
) -> str:
    """El encargo de un brazo: el mismo texto, con su cabeza y su número."""
    return BRIEF.format(
        n=n,
        p=p,
        head=HEAD_SENTENCE[arm],
        reproduced=reproduced,
        total=total,
        code=CODE_LINE if with_code else "",
    )


def brief_diff(first: str, second: str) -> str:
    """El diff entre dos encargos, para poder enseñar en qué se separan."""
    import difflib

    return "".join(
        difflib.unified_diff(
            first.splitlines(keepends=True),
            second.splitlines(keepends=True),
            fromfile="llm/BRIEF.md",
            tofile="rf/BRIEF.md",
            n=1,
        )
    )


# --- la auditoría -------------------------------------------------------

# Lo que no puede decir lo que redacta el arnés, además de lo que ya no podía
# decir en las piezas anteriores: aquí la respuesta es el sitio que ocupó cada
# petición en el lote, así que la narración tampoco puede nombrarlo.
#
# En `code/` estas palabras sí valen: el código dice lo que hace, y lo que hace
# es recorrer el índice en un orden que depende de la petición. Quitárselas
# sería esconder el sistema, no proteger la pregunta.
EXTRA_NARRATIVE = (
    "identificador", "posición", "posicion", "shard", "crc32", "zlib", "reintent",
)
NARRATIVE_FORBIDDEN = a5_case.NARRATIVE_FORBIDDEN + EXTRA_NARRATIVE
CODE_FORBIDDEN = a5_case.CODE_FORBIDDEN


def audit_package(root: Path) -> list[tuple[str, str]]:
    """Qué fichero del paquete dice qué palabra que no debería decir."""
    return a5_case.audit_package(root, narrative=NARRATIVE_FORBIDDEN, code=CODE_FORBIDDEN)


# --- los registros ------------------------------------------------------

# Campos que se caen del registro entregado. El identificador de la petición es
# su sitio en el lote, y el sitio en el lote es la respuesta.
DROPPED_FIELDS = ("run_id",)


def anonymous(trace_jsonl: str) -> str:
    """La traza somera, sin el identificador de la petición."""
    kept = Trace()
    for line in shallow(trace_jsonl).strip().splitlines():
        event = json.loads(line)
        payload = {k: v for k, v in event["payload"].items() if k not in DROPPED_FIELDS}
        kept.record(event["kind"], **payload)
    return kept.to_jsonl()


# --- la cabeza que viaja con el árbol -----------------------------------

RF_HEAD_SOURCE = Path(__file__).parents[1] / "variants" / "RF" / "model.py"
RF_HEAD_BLOB = Path(__file__).parents[3] / "data" / "rf" / "head.pkl"

# En el paquete la cabeza y su fichero van juntos, así que la ruta deja de
# apuntar al árbol del que se copió.
RF_HEAD_PATH_LINE = 'HEAD_PATH = Path(__file__).parents[4] / "data" / "rf" / "head.pkl"'
RF_HEAD_PATH_PACKAGED = 'HEAD_PATH = Path(__file__).parent / "head.pkl"'

# La cabeza del otro brazo se escribe aquí porque la que corrió vive en el
# arnés junto a cosas que el paquete no puede ver. Lo que hace es esto y nada
# más: mandar los mensajes y devolver el texto.
LLM_HEAD = '''"""Cabeza de clasificación construida sobre un modelo de lenguaje.

Cumple la misma interfaz que el resto del sistema espera: recibe la lista de
mensajes y devuelve el texto de la respuesta, que es el JSON con el código, la
confianza y la justificación.
"""

import os

# El despliegue que atiende las peticiones.
DEPLOYMENT = "gpt-5-mini"


class LanguageModelHead:
    """Manda los mensajes al despliegue y devuelve el texto que contesta."""

    def __init__(self, deployment: str = DEPLOYMENT) -> None:
        self.deployment = deployment

    def complete(self, messages: list[dict]) -> str:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_API_BASE"],
            api_key=os.environ["AZURE_API_KEY"],
            api_version=os.environ.get("AZURE_API_VERSION", "2025-04-01-preview"),
        )
        response = client.chat.completions.create(
            model=self.deployment, messages=messages
        )
        return response.choices[0].message.content or ""
'''


def write_head(arm: str, code: Path, *, blob: Path = RF_HEAD_BLOB) -> Path:
    """Escribe en el árbol entregado la cabeza de este brazo."""
    target = code / "head.py"
    if arm == "rf":
        source = RF_HEAD_SOURCE.read_text(encoding="utf-8")
        if RF_HEAD_PATH_LINE not in source:
            raise SystemExit("la cabeza del bosque ya no dice de dónde lee su fichero")
        target.write_text(
            source.replace(RF_HEAD_PATH_LINE, RF_HEAD_PATH_PACKAGED), encoding="utf-8"
        )
        shutil.copyfile(blob, code / "head.pkl")
    else:
        target.write_text(LLM_HEAD, encoding="utf-8")
    return target


# --- el paquete ---------------------------------------------------------


def build_case(
    passes: list[ArmPass],
    corpus: Path,
    out: Path,
    *,
    arm: str,
    with_code: bool,
    certification: Certification,
    work: Path | None = None,
    blob: Path = RF_HEAD_BLOB,
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
            with_code=with_code,
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

    if with_code:
        staging = (work or out.parent) / ".work-guardian-case"
        package = materialise(VARIANT, staging)
        shutil.copytree(package, out / "code", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.rmtree(staging, ignore_errors=True)
        write_head(arm, out / "code", blob=blob)

    flatten_clock(out)
    return out


def build_all(
    arms: dict[str, list[ArmPass]],
    corpus: Path,
    out_dir: Path,
    *,
    certifications: dict[str, Certification],
    work: Path | None = None,
    blob: Path = RF_HEAD_BLOB,
) -> dict[str, Path]:
    """Los cuatro paquetes, con y sin el código, para los dos brazos."""
    return {
        name: build_case(
            arms[arm],
            corpus,
            out_dir / name,
            arm=arm,
            with_code=with_code,
            certification=certifications[arm],
            work=work,
            blob=blob,
        )
        for name, (arm, with_code) in CASES.items()
    }


# --- línea de comandos --------------------------------------------------


def _pass_ids(runs: Path, arm: str) -> list[str]:
    return sorted(p.stem for p in (runs / arm).glob("pasada-*.json"))


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
    cases = build_all(
        arms,
        args.corpus,
        args.cases,
        certifications=certifications,
        work=args.work,
        blob=args.blob,
    )

    offences = {name: audit_package(path) for name, path in cases.items()}
    for name, found in offences.items():
        print(f"{name}: {len(audited(cases[name]))} ficheros auditados, {len(found)} hallazgos")
        for relative, word in found:
            print(f"    {relative}: {word!r}")

    diff = brief_diff(
        (cases["llm-sin"] / "BRIEF.md").read_text(encoding="utf-8"),
        (cases["rf-sin"] / "BRIEF.md").read_text(encoding="utf-8"),
    )
    print("\ndiff de los dos encargos:\n" + diff)

    args.frozen.parent.mkdir(parents=True, exist_ok=True)
    args.frozen.write_text(
        json.dumps(freeze(cases), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"congelado -> {args.frozen}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btm-guardian-case")
    parser.add_argument("--runs", type=Path, default=Path("results/guardian"))
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path(".work/guardian-case"))
    parser.add_argument("--blob", type=Path, default=RF_HEAD_BLOB)
    parser.add_argument("--frozen", type=Path, default=Path("results/frozen-guardian.json"))
    parser.set_defaults(fn=_report)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
