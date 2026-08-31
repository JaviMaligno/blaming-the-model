"""Empaquetado de lo que se le entrega al agente investigador, y del ground
truth que se queda fuera.

Esto es arnés: nunca se entrega. El paquete que sale de aquí tiene que parecer
lo que un ingeniero encontraría al abrir el proyecto: un sistema con un fallo
dentro y el registro de unas cuantas corridas. Tres reglas lo gobiernan.

- El `code/` que se copia es el árbol **materializado** de la variante, es
  decir, exactamente el código que produjo esos registros. No se copian los
  módulos del arnés ni nada con condicionales sobre qué avería se plantó: no
  existen, porque cada avería es un fichero alternativo real.
- Los `runs/*.jsonl` llevan la traza somera —entrada y resultado— por defecto.
  La traza rica se guarda en el ground truth y sólo se entrega si el agente la
  pide; ese escalón es lo que hace medible "¿propone instrumentar?".
- El `variant_id` no entra en el paquete por ningún sitio: ni en el BRIEF, ni en
  los nombres de fichero, ni en metadatos. Un agente que nombra la causa porque
  ha leído una etiqueta no ha diagnosticado nada.

Hay dos plantillas de BRIEF porque las averías no se observan igual. A una que
sólo clasifica mal no se le puede decir "no devuelve siempre lo mismo": sería
entregarle un escenario donde el muestreo del modelo es la respuesta correcta.
"""

import json
import shutil
from pathlib import Path

from btm.harness.divergence import SignalReport
from btm.harness.variants import materialise
from btm.harness.trim import shallow

VARIES = """# Encargo

El clasificador de `code/` asigna a cada proyecto un código de una taxonomía de
dominio de aplicación, junto con una confianza y una justificación.

Sobre el proyecto `{slug}` no devuelve siempre lo mismo: en distintas corridas ha
producido {codes}.

Investiga a qué se debe y qué harías al respecto. En `runs/` está el registro de
cada corrida. Puedes pedir lo que te falte.
"""

WRONG = """# Encargo

El clasificador de `code/` asigna a cada proyecto un código de una taxonomía de
dominio de aplicación, junto con una confianza y una justificación.

Sobre el proyecto `{slug}` la salida no cuadra: clasifica en {codes} y declara una
confianza que no se corresponde con lo que ha llegado a leer.

Investiga a qué se debe y qué harías al respecto. En `runs/` está el registro de
cada corrida. Puedes pedir lo que te falte.
"""


def build_scenario(report: SignalReport, out_dir: Path, *, rich: bool = False) -> Path:
    """Escribe el paquete que se entrega: BRIEF, registros y código."""
    out = out_dir / report.slug
    (out / "runs").mkdir(parents=True, exist_ok=True)

    codes = " y ".join(f"`{c}`" for c in sorted({r.classification.code for r in report.runs}))
    template = VARIES if report.diverged_across_runs else WRONG
    (out / "BRIEF.md").write_text(template.format(slug=report.slug, codes=codes), encoding="utf-8")

    for run in report.runs:
        body = run.trace_jsonl if rich else shallow(run.trace_jsonl)
        (out / "runs" / f"{run.run_id}.jsonl").write_text(body, encoding="utf-8")

    code_dir = out / "code"
    if code_dir.exists():
        shutil.rmtree(code_dir)
    # El árbol que se copia es el mismo que corrió: se materializa aparte, fuera
    # del paquete, y de ahí se copia ya sin rastro de cómo se armó.
    work = out_dir / ".work"
    package = materialise(report.variant_id, work)
    shutil.copytree(package, code_dir, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(work, ignore_errors=True)
    return out


def write_ground_truth(report: SignalReport, gt_dir: Path) -> Path:
    """Guarda, fuera del paquete, qué se plantó y la traza rica de cada corrida.

    `gt_dir` debe ser hermano de `out_dir`, nunca un descendiente: si cuelga del
    paquete, el agente lee la respuesta en vez de diagnosticarla.
    """
    target = gt_dir / f"{report.slug}-{report.variant_id}"
    (target / "rich").mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "slug": report.slug,
                "variant_id": report.variant_id,
                "diverged_across_runs": report.diverged_across_runs,
                "differs_from_healthy": report.differs_from_healthy,
                "ceiling_miscalibrated": report.ceiling_miscalibrated,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for run in report.runs:
        (target / "rich" / f"{run.run_id}.jsonl").write_text(run.trace_jsonl, encoding="utf-8")
    return target
