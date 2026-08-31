"""La cabeza de bosque aleatorio y el redondeo de la confianza.

La cabeza cumple la misma interfaz que el modelo —`complete(messages) -> str`
devolviendo el mismo JSON—, así que el resto del sistema no la distingue. Lo
que se comprueba aquí es justo eso: que es determinista, que su salida valida
contra el mismo esquema, que depende de los documentos que recibe y que la
confianza llega a la traza con la misma precisión venga de donde venga.
"""

import json
from pathlib import Path

import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer

from btm.system.classifier import Classification, build_prompt, classify
from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy
from btm.variants.RF.model import HEAD_PATH, RandomForestHead, save_head

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"

PAYMENTS = [
    "acme pay cobros facturas tarjeta comercio conciliacion",
    "acme pay pasarela de cobros facturas y recibos de comercio",
]
NETWORKING = [
    "acme pay proxy balanceador enrutado paquetes red",
    "acme pay malla de servicios proxy inverso y balanceador de red",
]


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


@pytest.fixture(scope="module")
def head(tmp_path_factory) -> RandomForestHead:
    """Una cabeza chica entrenada sobre dos vocabularios bien separados."""
    texts = PAYMENTS + NETWORKING
    codes = ["business.payments"] * len(PAYMENTS) + ["infra.networking"] * len(NETWORKING)
    vectorizer = TfidfVectorizer()
    forest = RandomForestClassifier(n_estimators=8, random_state=0)
    forest.fit(vectorizer.fit_transform(texts), codes)
    path = tmp_path_factory.mktemp("rf") / "head.pkl"
    save_head(vectorizer, forest, path, metadata={"model": "-", "trained_at": "-"})
    return RandomForestHead(path)


def snapshot(texts: list[str]) -> RepoSnapshot:
    return RepoSnapshot(
        slug="acme-pay",
        name="acme pay",
        description="SDK de cobros para comercios",
        documents=[
            Document(url=f"https://x.invalid/{i}", title=str(i), text=t, kind="docs")
            for i, t in enumerate(texts)
        ],
    )


def ask(head: RandomForestHead, prompt: str) -> dict:
    return json.loads(head.complete([{"role": "user", "content": prompt}]))


# --- la cabeza ----------------------------------------------------------


def test_the_head_answers_the_same_thing_to_the_same_prompt(head, taxonomy) -> None:
    prompt = build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS)
    messages = [{"role": "user", "content": prompt}]
    assert head.complete(messages) == head.complete(messages)


def test_a_head_reloaded_from_disk_answers_the_same_thing(head, taxonomy) -> None:
    prompt = build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS)
    reloaded = RandomForestHead(head.path)
    assert reloaded.complete([{"role": "user", "content": prompt}]) == head.complete(
        [{"role": "user", "content": prompt}]
    )


def test_the_answer_validates_against_the_same_schema(head, taxonomy) -> None:
    payload = ask(head, build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS))
    result = Classification.model_validate(payload)
    assert result.code in {leaf.code for leaf in taxonomy.leaves()}
    assert 0.0 <= result.confidence <= 1.0
    assert result.justification


def test_changing_the_documents_of_the_prompt_changes_the_answer(head, taxonomy) -> None:
    project = snapshot(PAYMENTS)
    assert ask(head, build_prompt(project, taxonomy, PAYMENTS))["code"] == "business.payments"
    assert ask(head, build_prompt(project, taxonomy, NETWORKING))["code"] == "infra.networking"


def test_the_answer_hangs_on_the_documents_and_not_on_the_metadata(head, taxonomy) -> None:
    """El mismo texto bajo otro nombre y otra descripción da lo mismo."""
    other = RepoSnapshot(slug="otro", name="otro", description="otra cosa", documents=[])
    first = build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS)
    second = build_prompt(other, taxonomy, PAYMENTS)
    assert first != second
    assert ask(head, first) == ask(head, second)


def test_the_justification_names_the_terms_that_weighed_most(head, taxonomy) -> None:
    payload = ask(head, build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS))
    terms = [t for t in ("cobros", "facturas", "tarjeta", "comercio") if t in payload["justification"]]
    assert terms


def test_the_head_declares_the_confidence_it_read_without_rounding(head, taxonomy) -> None:
    """La confianza sale de `predict_proba` tal cual: redondear es del sistema."""
    prompt = build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS)
    documents = "\n".join(PAYMENTS)
    proba = head.forest.predict_proba(head.vectorizer.transform([documents])).max()
    assert ask(head, prompt)["confidence"] == float(proba)


def test_the_trained_head_that_ships_with_the_corpus_loads_and_answers(taxonomy) -> None:
    shipped = RandomForestHead(HEAD_PATH)
    prompt = build_prompt(snapshot(PAYMENTS), taxonomy, PAYMENTS)
    payload = ask(shipped, prompt)
    assert Classification.model_validate(payload).code in {l.code for l in taxonomy.leaves()}
    assert ask(shipped, prompt) == payload


# --- el redondeo, en los dos brazos -------------------------------------


class FakeModel:
    """Un modelo que declara una confianza con más de dos decimales."""

    def complete(self, messages: list[dict]) -> str:
        return '{"code": "business.payments", "confidence": 0.8765, "justification": "-"}'


def test_the_model_head_reaches_the_trace_rounded_to_two_decimals(taxonomy) -> None:
    result, trace = classify(snapshot(PAYMENTS), taxonomy, FakeModel(), run_id="r0")
    assert result.confidence == 0.88
    assert _final(trace)["confidence"] == 0.88


def test_the_forest_head_reaches_the_trace_rounded_to_two_decimals(head, taxonomy) -> None:
    # Con una consulta menos de las planeadas el techo es 2/3, y es el techo
    # el que manda sobre una confianza más alta.
    result, trace = classify(
        snapshot(PAYMENTS), taxonomy, head, run_id="r0", max_searches=2
    )
    assert result.confidence == 0.67
    assert _final(trace)["confidence"] == 0.67


def test_both_heads_are_rounded_the_same(head, taxonomy) -> None:
    """Ninguna de las dos precisiones delata qué hay detrás."""
    forest, _ = classify(snapshot(PAYMENTS), taxonomy, head, run_id="r0", max_searches=2)
    model, _ = classify(snapshot(PAYMENTS), taxonomy, FakeModel(), run_id="r0", max_searches=2)
    assert forest.confidence == model.confidence


def _final(trace) -> dict:
    return next(e for e in trace.events if e.kind == "final").payload
