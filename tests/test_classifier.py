from pathlib import Path

from btm.system.classifier import Classification, classify, query_plan
from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"


class FakeModel:
    """Devuelve una respuesta fija, o una derivada del prompt recibido."""

    def __init__(self, reply="business.payments") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, messages: list[dict]) -> str:
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        code = self.reply(prompt) if callable(self.reply) else self.reply
        return f'{{"code": "{code}", "confidence": 0.9, "justification": "-"}}'


def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


def snapshot(description: str | None = "SDK de cobros para comercios") -> RepoSnapshot:
    # Los tres primeros mencionan el nombre, asi que los alcanza la consulta
    # inicial; los otros dos solo casan con consultas posteriores.
    texts = ["acme pay api cliente de cobros", "acme pay guia rapida",
             "acme pay referencia", "docs de instalacion", "notas de version"]
    return RepoSnapshot(
        slug="acme-pay",
        name="acme pay",
        description=description,
        documents=[
            Document(url=f"https://x.invalid/{i}", title=str(i), text=t, kind="docs")
            for i, t in enumerate(texts)
        ],
    )


def test_classifies_and_records_a_trace() -> None:
    result, trace = classify(snapshot(), taxonomy(), FakeModel(), run_id="r0")
    assert isinstance(result, Classification)
    assert result.code == "business.payments"
    assert [e.kind for e in trace.events][0] == "input"
    assert any(e.kind == "context_documents" for e in trace.events)


def test_the_input_event_carries_only_slug_and_run_id() -> None:
    _, trace = classify(snapshot(), taxonomy(), FakeModel(), run_id="r0")
    assert set(trace.events[0].payload) == {"slug", "run_id"}


def test_three_queries_are_planned_when_the_description_is_present() -> None:
    assert len(query_plan(snapshot())) == 3


def test_a_fourth_query_compensates_a_missing_description() -> None:
    assert len(query_plan(snapshot(description=None))) == 4


def test_a_healthy_run_answers_every_planned_query() -> None:
    _, trace = classify(snapshot(), taxonomy(), FakeModel(), run_id="r0")
    denied = [e for e in trace.events if e.kind == "tool_result" and e.payload.get("denied")]
    assert denied == []


def test_a_healthy_full_plan_does_not_cap_the_confidence() -> None:
    result, _ = classify(snapshot(), taxonomy(), FakeModel(), run_id="r0")
    assert result.confidence == 0.9


def test_three_documents_reach_the_model() -> None:
    _, trace = classify(snapshot(), taxonomy(), FakeModel(), run_id="r0")
    selected = next(e for e in trace.events if e.kind == "context_documents")
    assert len(selected.payload["urls"]) == 3


def test_the_healthy_prompt_carries_one_rule_only() -> None:
    model = FakeModel()
    classify(snapshot(), taxonomy(), model, run_id="r0")
    assert "dominio de aplicación principal" in model.prompts[0]
    assert "librería para desarrolladores" not in model.prompts[0]
