"""Las pasadas con dos cabezas y la certificación de estabilidad de cada una.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. Los snapshots
se construyen en memoria y las cabezas son dobles, así que la suite corre sin
red y sin modelo.
"""

import json
import threading
from pathlib import Path

import pytest

from btm.harness.guardian import (
    ArmPass,
    ProjectRun,
    build_parser,
    build_report,
    certify,
    changes,
    frozen_contexts,
    head_factory,
    head_fingerprint,
    pass_argv,
    project_run,
    request_id,
    resolve_head,
    run_pass,
    sha256_bytes,
)
from btm.harness.variants import load_classify
from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy
from tests.test_a5 import TAXONOMY_PATH, repository, write_corpus


def taxonomy() -> Taxonomy:
    return Taxonomy.load(TAXONOMY_PATH)


def tied(slug: str = "acme--pay", name: str = "pay", sections: int = 8) -> RepoSnapshot:
    """Un proyecto cuyas secciones puntúan todas igual.

    Con los empates a la vista, lo único que decide qué llega al modelo es el
    orden en que se recorre el índice.
    """
    owner = slug.split("--")[0]
    return RepoSnapshot(
        slug=slug,
        name=name,
        description="cobros con tarjeta",
        documents=[
            Document(
                url=f"https://github.com/{owner}/{name}#{i}",
                title="seccion",
                text=f"{name} seccion numero {i}",
                kind="readme",
            )
            for i in range(sections)
        ],
    )


class Deterministic:
    """Una cabeza que responde en función del texto que recibe, y sólo de él."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def code_for(self, prompt: str) -> str:
        return "business.payments" if "numero 0" in prompt else "infra.networking"

    def complete(self, messages: list[dict]) -> str:
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        return json.dumps(
            {"code": self.code_for(prompt), "confidence": 0.9, "justification": "-"}
        )


class Wobbly:
    """Una cabeza que ante el mismo texto no siempre responde lo mismo."""

    def __init__(self, *, every: int = 7, other: str = "data.storage") -> None:
        self.every = every
        self.other = other
        self.calls = 0
        self._lock = threading.Lock()

    def complete(self, messages: list[dict]) -> str:
        with self._lock:
            self.calls += 1
            n = self.calls
        code = self.other if n % self.every == 0 else "business.payments"
        return json.dumps({"code": code, "confidence": 0.9, "justification": "-"})


class Broken:
    """Una cabeza que devuelve algo que no es la respuesta acordada."""

    def complete(self, messages: list[dict]) -> str:
        return "no soy json"


def a_pass(arm: str, pass_id: str, labels: dict[str, str]) -> ArmPass:
    """Una pasada fabricada: sólo etiquetas, sin correr nada."""
    return ArmPass(
        arm=arm,
        pass_id=pass_id,
        hashseed=0,
        order=list(labels),
        projects=[
            ProjectRun(
                slug=slug,
                position=i,
                request_id=request_id(i, slug),
                code=code,
                confidence=0.9,
                justification="-",
                context_urls=[f"https://github.com/{slug}#0"],
                prompt_sha256=f"sha-{slug}",
                prompt_bytes=10,
                prompt=f"prompt de {slug}",
                trace_jsonl="",
            )
            for i, (slug, code) in enumerate(labels.items())
        ],
    )


# --- el identificador de la petición ------------------------------------


def test_the_request_identifier_carries_the_place_in_the_batch() -> None:
    assert request_id(0, "acme--pay") == "0:acme--pay"
    assert request_id(3, "acme--pay") != request_id(4, "acme--pay")


def test_the_place_in_the_batch_changes_what_the_search_returns(tmp_path: Path) -> None:
    """La avería sigue viva en este arnés: sin esto no hay nada que medir."""
    classify = load_classify("A1", tmp_path / "tree")
    snapshot = tied()
    contexts = {
        tuple(project_run(classify, snapshot, taxonomy(), Deterministic(), position).context_urls)
        for position in range(6)
    }
    assert len(contexts) > 1


def test_a_project_classified_twice_in_the_same_place_gets_the_same_context(
    tmp_path: Path,
) -> None:
    classify = load_classify("A1", tmp_path / "tree")
    snapshot = tied()
    first = project_run(classify, snapshot, taxonomy(), Deterministic(), 2)
    second = project_run(classify, snapshot, taxonomy(), Deterministic(), 2)
    assert first.context_urls == second.context_urls
    assert first.prompt_sha256 == second.prompt_sha256
    assert first.request_id == second.request_id == request_id(2, snapshot.slug)


# --- las pasadas --------------------------------------------------------


def small_corpus(tmp_path: Path) -> Path:
    return write_corpus(
        tmp_path / "corpus",
        [
            tied("acme--pay", "pay"),
            repository("globex", "mesh", "malla de servicios", "mesh malla kubernetes"),
            repository("initech", "flow", "tuberias de datos", "flow tuberias de datos"),
        ],
    )


def test_a_pass_classifies_every_project_and_keeps_its_order(tmp_path: Path) -> None:
    corpus = small_corpus(tmp_path)
    result = run_pass(
        "rf",
        "p1",
        seed=7,
        slugs=sorted(p.name for p in corpus.iterdir()),
        corpus=corpus,
        taxonomy_path=TAXONOMY_PATH,
        make_head=Deterministic,
        dest=tmp_path / "tree",
    )
    assert result.arm == "rf"
    assert result.hashseed == 7
    assert sorted(result.order) == ["acme--pay", "globex--mesh", "initech--flow"]
    assert [p.slug for p in result.projects] == result.order
    assert [p.position for p in result.projects] == [0, 1, 2]
    for project in result.projects:
        assert project.request_id == request_id(project.position, project.slug)
        assert project.prompt_bytes > 0
        assert project.context_urls
        assert project.trace_jsonl.strip()


def test_the_two_arms_get_exactly_the_same_context(tmp_path: Path) -> None:
    """Lo único que puede diferir entre brazos es la cabeza.

    El contexto se arma antes de llamar a la cabeza, así que el prompt de cada
    proyecto tiene que ser el mismo byte a byte en los dos brazos. Si no lo
    fuera, el control no compararía dos cabezas sino dos entradas.
    """
    corpus = small_corpus(tmp_path)
    slugs = sorted(p.name for p in corpus.iterdir())
    arms = {
        arm: run_pass(
            arm,
            "p1",
            seed=7,
            slugs=slugs,
            corpus=corpus,
            taxonomy_path=TAXONOMY_PATH,
            make_head=head,
            dest=tmp_path / f"tree-{arm}",
        )
        for arm, head in (("model", Wobbly), ("rf", Deterministic))
    }
    left, right = (arms["model"].by_slug(), arms["rf"].by_slug())
    assert left.keys() == right.keys()
    for slug in left:
        assert left[slug].prompt_sha256 == right[slug].prompt_sha256
        assert left[slug].context_urls == right[slug].context_urls


def test_a_pass_survives_a_head_that_answers_nonsense(tmp_path: Path) -> None:
    corpus = small_corpus(tmp_path)
    result = run_pass(
        "rf",
        "p1",
        seed=7,
        slugs=sorted(p.name for p in corpus.iterdir()),
        corpus=corpus,
        taxonomy_path=TAXONOMY_PATH,
        make_head=Broken,
        dest=tmp_path / "tree",
    )
    assert [p.code for p in result.projects] == ["", "", ""]
    assert all(p.failed for p in result.projects)


# --- quién cambia de etiqueta -------------------------------------------


def test_a_project_with_one_label_in_every_pass_does_not_change() -> None:
    passes = [a_pass("rf", f"p{n}", {"a--x": "ai.agents", "b--y": "data.storage"}) for n in (1, 2)]
    report = changes(passes)
    assert report.changing == []
    assert [p.count for p in report.per_pass] == [0, 0]


def test_the_change_is_counted_against_the_first_pass() -> None:
    passes = [
        a_pass("model", "p1", {"a--x": "ai.agents", "b--y": "data.storage"}),
        a_pass("model", "p2", {"a--x": "ai.serving", "b--y": "data.storage"}),
        a_pass("model", "p3", {"a--x": "ai.serving", "b--y": "infra.networking"}),
    ]
    report = changes(passes)
    assert report.changing == ["a--x", "b--y"]
    assert report.labels["a--x"] == ["ai.agents", "ai.serving", "ai.serving"]
    assert [(p.pass_id, p.count) for p in report.per_pass] == [("p1", 0), ("p2", 1), ("p3", 2)]
    assert report.per_pass[2].changed == ["a--x", "b--y"]


def test_a_project_missing_from_a_pass_is_not_a_change() -> None:
    passes = [
        a_pass("rf", "p1", {"a--x": "ai.agents", "b--y": "data.storage"}),
        a_pass("rf", "p2", {"a--x": "ai.agents"}),
    ]
    report = changes(passes)
    assert report.changing == []
    assert report.per_pass[1].changed == []


# --- la certificación ---------------------------------------------------


def test_the_frozen_context_is_the_one_of_the_first_pass_that_saw_the_project() -> None:
    passes = [
        a_pass("model", "p1", {"a--x": "ai.agents", "b--y": "data.storage"}),
        a_pass("model", "p2", {"a--x": "ai.serving", "b--y": "data.storage"}),
    ]
    contexts = frozen_contexts(passes, ["a--x"])
    assert [c.slug for c in contexts] == ["a--x"]
    assert contexts[0].pass_id == "p1"
    assert contexts[0].label == "ai.agents"
    assert contexts[0].prompt == "prompt de a--x"


def test_a_deterministic_head_reproduces_its_own_label_every_time() -> None:
    passes = [a_pass("rf", "p1", {"acme--pay": "business.payments"})]
    contexts = frozen_contexts(passes, ["acme--pay"])
    # La etiqueta congelada es la que la cabeza da a ese texto.
    contexts[0].label = Deterministic().code_for(contexts[0].prompt)
    certification = certify("rf", Deterministic, contexts, repeats=20)
    assert certification.repeats == 20
    assert certification.total == 20
    assert certification.reproduced == 20
    assert certification.fraction == 1.0
    assert certification.replays[0].codes == {"infra.networking": 20}


def test_a_wobbly_head_gets_the_number_it_gets() -> None:
    passes = [a_pass("model", "p1", {"acme--pay": "business.payments"})]
    contexts = frozen_contexts(passes, ["acme--pay"])
    head = Wobbly(every=7)
    certification = certify("model", lambda: head, contexts, repeats=20, workers=1)
    assert certification.reproduced == 18
    assert certification.total == 20
    assert certification.fraction == pytest.approx(0.9)
    assert certification.replays[0].codes == {"business.payments": 18, "data.storage": 2}


def test_an_unreadable_answer_counts_as_a_failure_and_not_as_a_reproduction() -> None:
    passes = [a_pass("model", "p1", {"acme--pay": "business.payments"})]
    contexts = frozen_contexts(passes, ["acme--pay"])
    certification = certify("model", Broken, contexts, repeats=5)
    assert certification.reproduced == 0
    assert certification.replays[0].failures == 5


def test_certifying_nothing_is_not_a_perfect_score() -> None:
    certification = certify("rf", Deterministic, [], repeats=20)
    assert certification.total == 0
    assert certification.fraction is None


# --- el informe ---------------------------------------------------------


def full_report() -> dict:
    arms = {
        "model": [
            a_pass("model", "p1", {"a--x": "ai.agents", "b--y": "data.storage"}),
            a_pass("model", "p2", {"a--x": "ai.serving", "b--y": "data.storage"}),
        ],
        "rf": [
            a_pass("rf", "p1", {"a--x": "devtools.build", "b--y": "data.storage"}),
            a_pass("rf", "p2", {"a--x": "devtools.build", "b--y": "data.storage"}),
        ],
    }
    certifications = {
        arm: certify(arm, Deterministic, frozen_contexts(passes, ["a--x"]), repeats=20)
        for arm, passes in arms.items()
    }
    return build_report(
        arms, certifications, corpus=Path("data/scenario"), seeds=[1, 2], repeats=20
    )


def test_the_report_carries_both_arms_with_who_changed_and_when() -> None:
    report = full_report()
    assert set(report["arms"]) == {"model", "rf"}
    assert report["arms"]["model"]["changing"] == ["a--x"]
    assert report["arms"]["rf"]["changing"] == []
    assert report["arms"]["model"]["per_pass"][1]["count"] == 1
    assert report["arms"]["model"]["certification"]["total"] == 20


def test_the_report_says_whether_the_two_arms_saw_the_same_input() -> None:
    report = full_report()
    assert report["same_context_across_arms"] is True
    assert report["context_mismatches"] == []


def test_the_report_reports_a_difference_in_input_instead_of_hiding_it() -> None:
    arms = {
        "model": [a_pass("model", "p1", {"a--x": "ai.agents"})],
        "rf": [a_pass("rf", "p1", {"a--x": "ai.agents"})],
    }
    arms["rf"][0].projects[0].prompt_sha256 = "otra-cosa"
    report = build_report(arms, {}, corpus=Path("data/scenario"), seeds=[1], repeats=20)
    assert report["same_context_across_arms"] is False
    assert report["context_mismatches"] == [{"pass_id": "p1", "slug": "a--x"}]


def test_the_report_is_json() -> None:
    assert json.loads(json.dumps(full_report(), ensure_ascii=False))["repeats"] == 20


# --- la cabeza se resuelve por su interfaz ------------------------------


def test_a_module_that_exposes_a_class_with_complete() -> None:
    class Module:
        Forest = Deterministic

    head = resolve_head(Module)()
    assert json.loads(head.complete([{"role": "user", "content": "numero 0"}]))["code"]


def test_a_module_that_exposes_a_factory() -> None:
    class Module:
        def make_head():  # noqa: N805 - módulo simulado, no una clase de verdad
            return Deterministic()

    assert hasattr(resolve_head(Module)(), "complete")


def test_a_module_that_only_exposes_the_function() -> None:
    class Module:
        def complete(messages):  # noqa: N805 - módulo simulado
            return '{"code": "ai.agents", "confidence": 1.0, "justification": "-"}'

    head = resolve_head(Module)()
    assert json.loads(head.complete([{"role": "user", "content": "x"}]))["code"] == "ai.agents"


def test_a_module_without_the_interface_says_so() -> None:
    class Module:
        VERSION = "1"

    with pytest.raises(TypeError, match="complete"):
        resolve_head(Module)


def test_the_forest_is_built_once_and_reused(monkeypatch) -> None:
    """Leer el bosque de disco en cada llamada costaría más que clasificar."""
    built = []

    def factory():
        built.append(1)
        return Deterministic()

    monkeypatch.setattr("btm.harness.guardian.forest_head", lambda: factory)
    make_head = head_factory("rf", deployment="-")
    assert make_head() is make_head()
    assert len(built) == 1


def test_each_call_to_the_model_gets_its_own_client() -> None:
    make_head = head_factory("model", deployment="gpt-5-mini")
    assert make_head() is not make_head()


def test_the_fingerprint_of_the_model_arm_is_its_deployment() -> None:
    assert head_fingerprint("model", Deterministic(), deployment="gpt-5-mini") == {
        "arm": "model",
        "head": "gpt-5-mini",
    }


def test_the_fingerprint_of_a_head_read_from_disk_carries_its_digest(
    tmp_path: Path, monkeypatch
) -> None:
    """Un bosque reentrenado a mitad de camino tiene que notarse en el informe."""
    blob = tmp_path / "data" / "head.pkl"
    blob.parent.mkdir()
    blob.write_bytes(b"un bosque")

    class Forest(Deterministic):
        path = blob

    monkeypatch.chdir(tmp_path)
    fingerprint = head_fingerprint("rf", Forest(), deployment="-")
    assert fingerprint["arm"] == "rf"
    assert fingerprint["head"] == "data/head.pkl"
    assert fingerprint["sha256"] == sha256_bytes(b"un bosque")


def test_the_fingerprint_never_writes_down_an_absolute_path(tmp_path: Path) -> None:
    """El informe se publica: no lleva dentro el directorio de nadie."""
    blob = tmp_path / "head.pkl"
    blob.write_bytes(b"un bosque")

    class Forest(Deterministic):
        path = blob

    assert head_fingerprint("rf", Forest(), deployment="-")["head"] == "head.pkl"


def test_the_report_carries_the_fingerprint_of_each_head() -> None:
    report = build_report(
        {"rf": [a_pass("rf", "p1", {"a--x": "ai.agents"})]},
        {},
        corpus=Path("data/scenario"),
        seeds=[1],
        repeats=20,
        heads=[{"arm": "rf", "head": "bosque"}],
    )
    assert report["heads"] == [{"arm": "rf", "head": "bosque"}]


def test_the_arguments_of_a_spawned_pass_are_the_ones_the_parser_expects() -> None:
    """Las opciones generales van antes del subcomando, o argparse las rechaza."""
    parser = build_parser()
    args = parser.parse_args(["--workers", "4", "all"])
    spawned = parser.parse_args(pass_argv(args, "rf", "pasada-3", 33))
    assert (spawned.stage, spawned.arm, spawned.pass_id, spawned.seed) == (
        "pass",
        "rf",
        "pasada-3",
        33,
    )
    assert spawned.workers == 4
