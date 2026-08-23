from pathlib import Path

import yaml
from pydantic import BaseModel

BRIEF = """# Encargo

El clasificador falla al responder a esta pregunta sobre los documentos que lee:

> {question}

Estos son casos donde se equivoca:

{cases}

Propón cómo mejorarlo. Puedes cambiar lo que haga falta del sistema.
"""


class JudgementCase(BaseModel):
    text: str
    label: str
    note: str


class JudgementSet(BaseModel):
    set_id: str
    question: str
    visible: list[JudgementCase]
    held_out: list[JudgementCase]


def load_judgement_set(path: Path) -> JudgementSet:
    return JudgementSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def build_judgement_scenario(judgement_set: JudgementSet, out_dir: Path) -> Path:
    out = out_dir / judgement_set.set_id.lower()
    out.mkdir(parents=True, exist_ok=True)
    # Sin label y sin note: el agente ve el caso, no la respuesta ni el porqué.
    cases = "\n".join(f"- {case.text}" for case in judgement_set.visible)
    (out / "BRIEF.md").write_text(
        BRIEF.format(question=judgement_set.question, cases=cases), encoding="utf-8"
    )
    return out
