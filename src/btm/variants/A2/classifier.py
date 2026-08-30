"""Clasificación de un repositorio en un código de la taxonomía.

El flujo es: se planean las consultas a partir de los metadatos del
repositorio, se lanzan contra el índice mientras quede presupuesto, se llevan
al modelo los primeros documentos recuperados y se acota la confianza de la
respuesta según la evidencia conseguida.
"""

import json

from pydantic import BaseModel

from btm.system.budget import Budget, SearchBudgetExhausted
from btm.system.corpus import RepoSnapshot
from btm.system.model import Model
from btm.system.taxonomy import Taxonomy
from btm.system.tools import ToolBox
from btm.system.trace import Trace

# Número de documentos recuperados que se adjuntan al prompt.
CONTEXT_DOCUMENTS = 4
RULE = "Clasifica por el dominio de aplicación principal del proyecto."


class Classification(BaseModel):
    """El código elegido, con su confianza y el motivo que dio el modelo."""

    code: str
    confidence: float
    justification: str


def query_plan(snapshot: RepoSnapshot) -> list[str]:
    """Las consultas que se lanzarán para este repositorio."""
    name = snapshot.name.replace("-", " ")
    return [
        name,
        f"{name} installation usage instalacion uso",
        f"{name} features examples caracteristicas ejemplos",
    ]


def build_prompt(snapshot: RepoSnapshot, taxonomy: Taxonomy, documents: list[str]) -> str:
    """Arma el mensaje que se le manda al modelo."""
    codes = "\n".join(f"- {leaf.code}: {leaf.name}" for leaf in taxonomy.leaves())
    return (
        f"Proyecto: {snapshot.name}\n"
        f"Descripción: {snapshot.description or '(no disponible)'}\n"
        f"{RULE}\n"
        f"Taxonomía:\n{codes}\n"
        "Documentos:\n" + "\n---\n".join(documents) + "\n"
        'Responde JSON: {"code": ..., "confidence": ..., "justification": ...}'
    )


def classify(
    snapshot: RepoSnapshot,
    taxonomy: Taxonomy,
    model: Model,
    *,
    run_id: str,
    max_searches: int = 4,
) -> tuple[Classification, Trace]:
    """Clasifica un repositorio y devuelve el resultado junto con su traza."""
    trace = Trace()
    trace.record("input", slug=snapshot.slug, run_id=run_id)

    budget = Budget(max_searches)
    tools = ToolBox(snapshot, taxonomy, run_id=run_id)

    queries = query_plan(snapshot)
    per_query: list[list[str]] = []
    answered = 0
    for query in queries:
        try:
            budget.spend()
        except SearchBudgetExhausted:
            trace.record("tool_result", name="search", query=query, urls=[], denied=True)
            break
        trace.record("tool_call", name="search", query=query)
        found = tools.search(query)
        answered += 1
        trace.record("tool_result", name="search", query=query, urls=[h.url for h in found])
        per_query.append([h.url for h in found])

    ceiling = budget.declared_ceiling(answered=answered, planned=len(queries))
    trace.record(
        "budget", remaining=budget.remaining, answered=answered,
        planned=len(queries), declared_ceiling=ceiling,
    )

    # El contexto se reparte entre las consultas: cada una cede su mejor
    # resultado antes de que ninguna ceda el segundo.
    ordered: list[str] = []
    seen: set[str] = set()
    for depth in range(max((len(urls) for urls in per_query), default=0)):
        for urls in per_query:
            if depth < len(urls) and urls[depth] not in seen:
                seen.add(urls[depth])
                ordered.append(urls[depth])
        if len(ordered) >= CONTEXT_DOCUMENTS:
            break
    ordered = ordered[:CONTEXT_DOCUMENTS]
    trace.record("context_documents", urls=ordered)
    documents = [tools.fetch_page(url) for url in ordered]

    prompt = build_prompt(snapshot, taxonomy, documents)
    trace.record("model_message", prompt=prompt)
    payload = json.loads(model.complete([{"role": "user", "content": prompt}]))

    result = Classification(
        code=payload["code"],
        confidence=min(float(payload["confidence"]), ceiling),
        justification=payload["justification"],
    )
    trace.record("final", code=result.code, confidence=result.confidence)
    return result, trace
