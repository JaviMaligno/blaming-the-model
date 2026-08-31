"""La cabeza que sirve la clasificación ya emitida, y lo que no cambia con ella.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. El almacén se
construye en memoria y ninguna prueba toca la red.

Lo que se comprueba es lo mismo que se le exigió a la cabeza de bosque —misma
interfaz, determinista, salida contra el mismo esquema— más las dos cosas que
justifican que exista: que la fracción de reproducción sale entera, y que la
variabilidad entre pasadas sigue donde estaba, porque el orden de recuperación
se decide antes de llamar a la cabeza y el contexto cambia de una pasada a
otra.
"""

import importlib
import json
import shutil
from pathlib import Path

import pytest

from btm.harness import answers as store
from btm.harness.a5_case import CODE_FORBIDDEN
from btm.harness.guardian_case import audit_package
from btm.harness.guardian import (
    ArmPass,
    certify,
    changes,
    frozen_contexts,
    head_factory,
    head_fingerprint,
    project_run,
    resolve_head,
    run_pass,
)
from btm.harness.variants import load_classify
from btm.system.classifier import Classification, build_prompt
from btm.system.taxonomy import Taxonomy
from btm.variants.CACHED.head import HEAD_PATH, CachedHead, key_of, save_answers
from tests.test_a5 import TAXONOMY_PATH
from tests.test_guardian import Deterministic, small_corpus, taxonomy, tied

HEAD_SOURCE = Path(__file__).parents[1] / "src" / "btm" / "variants" / "CACHED" / "head.py"

# Lo que no puede aparecer en un fichero que se entrega junto al sistema: la
# cabeza lee de disco, y quien la abra no tiene que encontrarse una llamada a
# ningún sitio.
NETWORK_WORDS = (
    "openai", "azure", "api_key", "apikey", "endpoint", "deployment",
    "http", "client", "requests", "urllib", "socket", "token",
)


def answer(code: str, confidence: float = 0.92, justification: str = "-") -> str:
    return json.dumps(
        {"code": code, "confidence": confidence, "justification": justification},
        ensure_ascii=False,
    )


@pytest.fixture
def stored(tmp_path: Path) -> CachedHead:
    """Un almacén chico con dos contextos dentro."""
    save_answers(
        {
            key_of("cobros con tarjeta"): answer("business.payments"),
            key_of("malla de servicios"): answer("infra.networking", 0.81, "malla"),
        },
        tmp_path / "head.pkl",
        metadata={"model": "-", "written_at": "-"},
    )
    return CachedHead(tmp_path / "head.pkl")


def ask(head: CachedHead, prompt: str) -> dict:
    return json.loads(head.complete([{"role": "user", "content": prompt}]))


# --- la clave -----------------------------------------------------------


def test_the_same_context_gets_the_same_key() -> None:
    assert key_of("un texto largo\ncon saltos") == key_of("un texto largo\ncon saltos")


def test_two_contexts_that_differ_in_one_byte_get_different_keys() -> None:
    assert key_of("documento a") != key_of("documento b")


# --- la cabeza ----------------------------------------------------------


def test_the_head_answers_the_same_thing_to_the_same_prompt(stored) -> None:
    messages = [{"role": "user", "content": "cobros con tarjeta"}]
    assert len({stored.complete(messages) for _ in range(20)}) == 1


def test_a_head_reloaded_from_disk_answers_the_same_thing(stored) -> None:
    reloaded = CachedHead(stored.path)
    messages = [{"role": "user", "content": "cobros con tarjeta"}]
    assert reloaded.complete(messages) == stored.complete(messages)


def test_the_answer_validates_against_the_same_schema(stored) -> None:
    result = Classification.model_validate(ask(stored, "cobros con tarjeta"))
    assert result.code == "business.payments"
    assert 0.0 <= result.confidence <= 1.0
    assert result.justification


def test_changing_the_context_changes_the_answer(stored) -> None:
    assert ask(stored, "cobros con tarjeta")["code"] == "business.payments"
    assert ask(stored, "malla de servicios")["code"] == "infra.networking"


def test_a_context_that_is_not_in_the_store_says_which_one(stored) -> None:
    with pytest.raises(KeyError, match=key_of("otra cosa")):
        stored.complete([{"role": "user", "content": "otra cosa"}])


def test_the_head_carries_the_file_it_read_and_its_metadata(stored) -> None:
    assert stored.path.exists()
    assert stored.metadata["model"] == "-"


# --- la cabeza dentro del sistema ---------------------------------------


def test_the_system_classifies_a_project_with_the_head_reading_from_disk(
    tmp_path: Path,
) -> None:
    """El clasificador no distingue esta cabeza de ninguna otra."""
    classify = load_classify("A1", tmp_path / "tree")
    snapshot = tied()
    recorded = project_run(classify, snapshot, taxonomy(), Deterministic(), 3)

    save_answers(
        {key_of(recorded.prompt): answer(recorded.code, recorded.confidence)},
        tmp_path / "head.pkl",
    )
    served = project_run(
        classify, snapshot, taxonomy(), CachedHead(tmp_path / "head.pkl"), 3
    )
    assert not served.failed
    assert served.code == recorded.code
    assert served.confidence == recorded.confidence
    assert served.prompt_sha256 == recorded.prompt_sha256


def test_the_confidence_reaches_the_trace_with_the_same_precision(tmp_path: Path) -> None:
    """Ninguna precisión delata qué hay detrás de la cabeza."""
    classify = load_classify("A1", tmp_path / "tree")
    snapshot = tied()
    prompt = project_run(classify, snapshot, taxonomy(), Deterministic(), 0).prompt
    save_answers({key_of(prompt): answer("business.payments", 0.8765)}, tmp_path / "head.pkl")
    served = project_run(classify, snapshot, taxonomy(), CachedHead(tmp_path / "head.pkl"), 0)
    assert served.confidence == 0.88


# --- la certificación ---------------------------------------------------


def test_the_head_reproduces_every_frozen_context_every_time(tmp_path: Path) -> None:
    """La fracción de reproducción de una cabeza que lee de disco sale entera."""
    classify = load_classify("A1", tmp_path / "tree")
    runs = [
        project_run(classify, tied(f"acme--p{n}", f"p{n}"), taxonomy(), Deterministic(), n)
        for n in range(3)
    ]
    save_answers(
        {key_of(run.prompt): answer(run.code, run.confidence) for run in runs},
        tmp_path / "head.pkl",
    )
    passes = [
        ArmPass(
            arm="cached",
            pass_id="pasada-1",
            hashseed=0,
            order=[run.slug for run in runs],
            projects=runs,
        )
    ]
    contexts = frozen_contexts(passes, [run.slug for run in runs])

    certification = certify(
        "cached", lambda: CachedHead(tmp_path / "head.pkl"), contexts, repeats=20
    )
    assert certification.total == 60
    assert certification.reproduced == 60
    assert certification.fraction == 1.0
    assert all(replay.failures == 0 for replay in certification.replays)


# --- la variabilidad entre pasadas --------------------------------------


def rotated_passes(tmp_path: Path, head_of, *, turns: int = 3) -> list:
    """Las mismas pasadas con los proyectos en sitios distintos del lote."""
    corpus = small_corpus(tmp_path)
    slugs = sorted(p.name for p in corpus.iterdir())
    passes = []
    for turn in range(turns):
        order = slugs[turn:] + slugs[:turn]
        passes.append(
            run_pass(
                "cached",
                f"pasada-{turn + 1}",
                seed=turn,
                slugs=order,
                corpus=corpus,
                taxonomy_path=TAXONOMY_PATH,
                make_head=head_of,
                dest=tmp_path / f"tree-{turn}",
                workers=2,
            )
        )
    return passes


def test_the_store_serves_every_context_of_every_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("btm.harness.guardian.set_order", lambda slugs: list(slugs))
    recorded = rotated_passes(tmp_path, Deterministic)
    save_answers(store.harvest(recorded), tmp_path / "head.pkl")
    assert store.missing(recorded, store.harvest(recorded)) == []

    served = rotated_passes(tmp_path, lambda: CachedHead(tmp_path / "head.pkl"))
    for before, after in zip(recorded, served):
        assert {s: r.code for s, r in before.by_slug().items()} == {
            s: r.code for s, r in after.by_slug().items()
        }


def test_the_variability_between_passes_survives_the_store(
    tmp_path: Path, monkeypatch
) -> None:
    """La causa está aguas arriba de la cabeza, así que guardar no la apaga.

    El contexto de un proyecto depende del sitio que ocupa en el lote, y ese
    sitio cambia de una pasada a otra: la clave cambia con él y el almacén
    devuelve otra cosa.
    """
    monkeypatch.setattr("btm.harness.guardian.set_order", lambda slugs: list(slugs))
    recorded = rotated_passes(tmp_path, Deterministic)
    assert changes(recorded).changing, "sin variabilidad medida no hay nada que comparar"

    save_answers(store.harvest(recorded), tmp_path / "head.pkl")
    served = rotated_passes(tmp_path, lambda: CachedHead(tmp_path / "head.pkl"))

    assert changes(served).changing == changes(recorded).changing
    assert [p.count for p in changes(served).per_pass] == [
        p.count for p in changes(recorded).per_pass
    ]
    assert any(p.count for p in changes(served).per_pass)


# --- lo que el arnés pide de ella ---------------------------------------


def test_the_module_of_the_head_resolves_by_the_interface() -> None:
    """El arnés no le impone un nombre a la cabeza: le exige `complete`."""
    assert resolve_head(importlib.import_module("btm.variants.CACHED.head")) is CachedHead


def test_the_arm_builds_its_head_once_and_reuses_it(tmp_path: Path, monkeypatch) -> None:
    """Leer el almacén en cada llamada costaría más que servir la respuesta."""
    save_answers({key_of("x"): answer("ai.agents")}, tmp_path / "head.pkl")
    monkeypatch.setattr(
        "btm.harness.guardian.stored_head",
        lambda: (lambda: CachedHead(tmp_path / "head.pkl")),
    )
    make_head = head_factory("cached", deployment="-")
    assert make_head() is make_head()
    assert ask(make_head(), "x")["code"] == "ai.agents"


def test_the_store_that_ships_with_the_corpus_loads_and_answers() -> None:
    shipped = CachedHead(HEAD_PATH)
    assert len(shipped) > 0
    payload = json.loads(next(iter(shipped.answers.values())))
    assert Classification.model_validate(payload).code
    assert shipped.metadata["answers"] == len(shipped)


def test_the_fingerprint_of_the_stored_arm_carries_the_digest_of_its_file(
    tmp_path: Path, monkeypatch
) -> None:
    save_answers({key_of("x"): answer("ai.agents")}, tmp_path / "head.pkl")
    monkeypatch.chdir(tmp_path)
    fingerprint = head_fingerprint("cached", CachedHead(tmp_path / "head.pkl"), deployment="-")
    assert fingerprint == {
        "arm": "cached",
        "head": "head.pkl",
        "sha256": fingerprint["sha256"],
    }
    assert len(fingerprint["sha256"]) == 64


# --- lo que el fichero entregado no puede decir --------------------------


def test_the_delivered_head_says_nothing_it_should_not() -> None:
    body = HEAD_SOURCE.read_text(encoding="utf-8").lower()
    assert [word for word in CODE_FORBIDDEN if word in body] == []


def test_the_delivered_head_calls_nobody(tmp_path: Path) -> None:
    """Lee de disco y nada más: no hay ningún servicio al que culpar."""
    body = HEAD_SOURCE.read_text(encoding="utf-8").lower()
    assert [word for word in NETWORK_WORDS if word in body] == []


def test_the_delivered_head_is_the_whole_module(tmp_path: Path) -> None:
    """Nada de lo que importa la cabeza viene de fuera del sistema entregado."""
    body = HEAD_SOURCE.read_text(encoding="utf-8")
    assert "from btm" not in body
    assert "import btm" not in body


def test_a_tree_with_this_head_and_its_file_passes_the_audit(tmp_path: Path) -> None:
    """Lo que viaja con el árbol se audita con la misma lista que el resto."""
    code = tmp_path / "caso" / "code"
    code.mkdir(parents=True)
    (code / "head.py").write_text(HEAD_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copyfile(HEAD_PATH, code / "head.pkl")
    assert audit_package(tmp_path / "caso") == []


# --- lo que el almacén no puede tapar -----------------------------------


def test_two_codes_for_the_same_context_are_reported_and_not_chosen_between(
    tmp_path: Path, monkeypatch
) -> None:
    """Guardar una de dos clasificaciones del mismo texto sería elegir por la cabeza."""
    monkeypatch.setattr("btm.harness.guardian.set_order", lambda slugs: list(slugs))
    passes = rotated_passes(tmp_path, Deterministic, turns=2)
    assert store.conflicts(passes) == []

    twice = passes[0].projects[0]
    passes[1].projects[0].prompt = twice.prompt
    passes[1].projects[0].code = "data.storage"
    passes[1].projects[0].slug = twice.slug
    found = store.conflicts(passes)
    assert len(found) == 1
    assert found[0]["codes"] == sorted({twice.code, "data.storage"})
