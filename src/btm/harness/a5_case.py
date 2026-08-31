"""Armado de los dos paquetes que se entregan, y su congelación.

Esto es arnés: nunca se entrega, y lo que sale de aquí sí. Tres reglas lo
gobiernan, heredadas de `btm.harness.scenario`:

- Las trazas van someras: entrada y resultado, renumeradas desde cero. Nada de
  marcas de tiempo, posiciones ni conteos: el registro no puede decir en qué
  orden se atendió a cada proyecto, porque ése es justo el dato que hay que
  reconstruir razonando.
- El `code/` que se copia es el árbol materializado que produjo esos registros,
  sin el arnés y sin el registrador.
- El BRIEF cuenta el síntoma como lo contaría el equipo que lo sufre: el lote no
  devuelve siempre lo mismo y el proyecto suelto sale bien. Nada más.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from btm.harness.passes import PassResult
from btm.harness.trim import shallow
from btm.harness.variants import materialise

BRIEF = """# Encargo

El clasificador asigna a cada proyecto de software un código de una taxonomía de
dominio de aplicación, junto con una confianza y una justificación. Se ejecuta
todas las noches sobre el catálogo entero, {n} proyectos, en una sola pasada.

El resultado no es siempre el mismo. Comparando las últimas {p} pasadas, unos
pocos proyectos aparecen con un código distinto de una noche a otra; el resto no
se mueve. Cuáles son esos proyectos tampoco es siempre igual.

Cuando cogemos uno de los proyectos afectados y lo volvemos a clasificar por
separado, sale bien: la etiqueta que esperábamos, y la misma todas las veces.

En `pasadas.md` está el código asignado a cada proyecto en cada pasada, y en
`runs/` el registro de cada corrida. En `corpus/` están los documentos con los
que trabajó.{code}

Investiga a qué se debe y qué harías al respecto. Puedes pedir lo que te falte.
"""

CODE_LINE = " En `code/` está el sistema."

PASADAS = """# Pasadas del catálogo

Código asignado a cada proyecto en cada una de las {p} pasadas.

| proyecto | {heads} |
|---|{rule}
{rows}
"""


def _table(passes: list[PassResult]) -> str:
    slugs = sorted({p.slug for result in passes for p in result.projects})
    by_pass = [result.by_slug() for result in passes]
    rows = []
    for slug in slugs:
        cells = [f"`{p[slug].code}`" if slug in p else "—" for p in by_pass]
        rows.append(f"| {slug} | " + " | ".join(cells) + " |")
    return PASADAS.format(
        p=len(passes),
        heads=" | ".join(result.pass_id for result in passes),
        rule="---|" * len(passes),
        rows="\n".join(rows),
    )


def build_case(
    passes: list[PassResult],
    corpus: Path,
    out: Path,
    *,
    with_code: bool,
    work: Path | None = None,
) -> Path:
    """Escribe el paquete: encargo, tabla de pasadas, registros y corpus."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    projects = sorted({p.slug for result in passes for p in result.projects})
    (out / "BRIEF.md").write_text(
        BRIEF.format(n=len(projects), p=len(passes), code=CODE_LINE if with_code else ""),
        encoding="utf-8",
    )
    (out / "pasadas.md").write_text(_table(passes), encoding="utf-8")

    for result in passes:
        target = out / "runs" / result.pass_id
        target.mkdir(parents=True, exist_ok=True)
        # Por slug, no por posición: el nombre del fichero no dice cuándo se
        # atendió a cada proyecto.
        for project in sorted(result.projects, key=lambda p: p.slug):
            (target / f"{project.slug}.jsonl").write_text(
                shallow(project.trace_jsonl), encoding="utf-8"
            )

    shutil.copytree(
        corpus, out / "corpus", ignore=shutil.ignore_patterns("__pycache__", "README.md")
    )

    if with_code:
        staging = (work or out.parent) / ".work-a5-case"
        package = materialise("A5", staging)
        shutil.copytree(package, out / "code", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.rmtree(staging, ignore_errors=True)

    flatten_clock(out)
    return out


# Un segundo entre fichero y fichero: suficiente para que el orden se vea y no
# tan fino como para que parezca puesto a mano.
CLOCK_STEP = 1


def flatten_clock(root: Path, *, start: float = 946_684_800.0) -> None:
    """Reordena las fechas de modificación del paquete por orden alfabético.

    `copytree` conserva la fecha de cada snapshot, y ésas llevan dentro el
    orden en que se capturaron: los proyectos que interesan se capturaron
    primero y un `ls -lt` los pondría los primeros de la lista. La fecha de
    modificación de un fichero copiado no es un dato del caso, así que se
    sustituye por una que no dice nada: la del recorrido alfabético del propio
    paquete, de dentro afuera para que los directorios no se rehagan solos.
    """
    paths = sorted(root.rglob("*"))
    stamps = {path: start + CLOCK_STEP * n for n, path in enumerate(paths, 1)}
    # De dentro afuera: tocar un fichero rehace la fecha de su directorio.
    for path in reversed(paths):
        os.utime(path, (stamps[path], stamps[path]))
    os.utime(root, (start, start))


# Dos listas, porque no se le pide lo mismo a los dos sitios.
#
# Lo que el arnés redacta —el encargo, la tabla y los registros— no puede
# nombrar ni el mecanismo ni ninguna de sus hipótesis rivales: decir «memoria»
# o decir «muestreo» sería contestar por adelantado, cada una en una dirección.
#
# El código sí habla de memoización, porque de eso trata y así lo escribiría
# cualquiera de buena fe. Lo que no puede es hablar del trabajo del que forma
# parte, ni traer nada del arnés.
NARRATIVE_FORBIDDEN = (
    "avería", "averia", "bug", "escenario", "experimento", "variante",
    "estocást", "estocast", "envenenad", "arnés", "arnes", "caché", "cache",
    "memoiza", "muestreo", "temperatura", "seed", "hashseed", "colisión",
    "colision", "contaminad", "donante", "víctima", "victima",
    "a1", "a2", "a3", "a4", "a5",
)
CODE_FORBIDDEN = (
    "avería", "averia", "bug", "escenario", "experimento", "variante",
    "estocást", "estocast", "envenenad", "arnés", "arnes", "harness",
    "contaminad", "donante", "víctima", "victima", "sha256", "registrador",
    "a1", "a2", "a3", "a4", "a5",
)

# El corpus queda fuera de la auditoría: es prosa de terceros escrita antes de
# que existiera nada de esto, y una coincidencia suya no dice nada.
AUDITED_SUFFIXES = (".md", ".jsonl", ".py", ".json")


def audited(root: Path) -> list[Path]:
    """Los ficheros del paquete que salieron de aquí, sin el corpus."""
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "corpus" not in path.relative_to(root).parts
        and path.suffix in AUDITED_SUFFIXES
    ]


def audit_package(root: Path) -> list[tuple[str, str]]:
    """Qué fichero dice qué palabra que no debería decir."""
    offences: list[tuple[str, str]] = []
    for path in audited(root):
        relative = path.relative_to(root)
        words = CODE_FORBIDDEN if relative.parts[0] == "code" else NARRATIVE_FORBIDDEN
        body = path.read_text(encoding="utf-8").lower()
        offences += [(str(relative), word) for word in words if word in body]
    return offences


def freeze(cases: dict[str, Path]) -> dict:
    """Digest por fichero y digest del paquete entero."""
    frozen: dict[str, dict] = {}
    for name, root in cases.items():
        manifest = {}
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            manifest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        rolled = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        frozen[name] = {"files": len(manifest), "digest": rolled, "manifest": manifest}
    return frozen
