from pathlib import Path

from btm.harness.divergence import collect
from btm.system.corpus import Document, RepoSnapshot
from btm.system.taxonomy import Taxonomy

TAXONOMY_PATH = Path(__file__).parents[1] / "data" / "taxonomy.yaml"


class DocumentSensitiveModel:
    """Responde según los documentos que le hayan llegado en el prompt."""

    def complete(self, messages: list[dict]) -> str:
        prompt = messages[0]["content"]
        code = "business.payments" if "cobros" in prompt else "devtools.libraries"
        return f'{{"code": "{code}", "confidence": 0.9, "justification": "-"}}'


def _snapshot(slug: str, texts: list[str]) -> RepoSnapshot:
    return RepoSnapshot(
        slug=slug,
        name="acme pay",
        description=None,
        documents=[
            Document(url=f"https://x.invalid/{i}", title=str(i), text=t, kind="docs")
            for i, t in enumerate(texts)
        ],
    )


def tied_snapshot() -> RepoSnapshot:
    """Seis documentos que empatan: cuáles caben en el contexto decide la respuesta.

    Todos mencionan el nombre, así que todos puntúan igual en cada consulta y el
    desempate lo decide el orden del índice. Sólo uno habla de cobros, y en el
    orden estable queda fuera de los tres primeros.
    """
    return _snapshot(
        "empates",
        [
            "acme pay libreria de utilidades",
            "acme pay helpers de integracion",
            "acme pay referencia de tipos",
            "acme pay cobros para comercios",
            "acme pay ejemplos de uso",
            "acme pay guia de estilo",
        ],
    )


def late_evidence_snapshot() -> RepoSnapshot:
    """La evidencia que identifica el proyecto sólo la alcanza la última consulta.

    Cada sección responde a una consulta distinta del plan, y la única que dice
    a qué se dedica el proyecto es la que habla de su propósito: no la alcanza
    ninguna de las tres consultas iniciales.
    """
    sections = [
        ("acme pay", "acme pay"),
        ("Installation", "installation usage guide steps"),
        ("Features", "features examples of the helpers"),
        ("About", "overview purpose we process cobros for comercios"),
        ("Changelog", "version notes"),
        ("License", "mit"),
    ]
    return RepoSnapshot(
        slug="evidencia-tardia",
        name="acme pay",
        description=None,
        documents=[
            Document(url=f"https://x.invalid/{i}", title=title, text=text, kind="docs")
            for i, (title, text) in enumerate(sections)
        ],
    )


def _collect(snapshot, variant_id, tmp_path, runs=8):
    return collect(
        snapshot,
        Taxonomy.load(TAXONOMY_PATH),
        DocumentSensitiveModel,
        variant_id=variant_id,
        run_ids=[f"r{i}" for i in range(runs)],
        workdir=tmp_path,
    )


def test_a1_diverges_across_runs(tmp_path: Path) -> None:
    report = _collect(tied_snapshot(), "A1", tmp_path)
    assert report.diverged_across_runs is True


def test_a3_diverges_across_runs(tmp_path: Path) -> None:
    report = _collect(tied_snapshot(), "A3", tmp_path)
    assert report.diverged_across_runs is True


def test_the_healthy_system_does_not_diverge(tmp_path: Path) -> None:
    # La línea base sobre el mismo corpus: sin la avería, el orden es estable.
    report = _collect(tied_snapshot(), "A1", tmp_path)
    assert len({run.classification.code for run in report.healthy_runs}) == 1


def test_a2_does_not_diverge_but_differs_from_healthy(tmp_path: Path) -> None:
    report = _collect(late_evidence_snapshot(), "A2", tmp_path)
    assert report.diverged_across_runs is False
    assert report.differs_from_healthy is True


def test_a4_differs_from_healthy_and_inflates_the_ceiling(tmp_path: Path) -> None:
    report = _collect(late_evidence_snapshot(), "A4", tmp_path)
    assert report.diverged_across_runs is False
    assert report.differs_from_healthy is True
    assert report.ceiling_miscalibrated is True


def test_differing_from_healthy_means_a_different_answer(tmp_path: Path) -> None:
    # La señal compara lo que el sistema publica, no su traza: cualquier avería
    # cambia algún evento interno, así que incluir la traza la haría trivial.
    report = _collect(late_evidence_snapshot(), "A4", tmp_path)
    pairs = list(zip(report.runs, report.healthy_runs))
    assert any(a.classification.code != b.classification.code for a, b in pairs)


def test_healthy_runs_are_collected_alongside(tmp_path: Path) -> None:
    report = _collect(late_evidence_snapshot(), "A2", tmp_path, runs=2)
    assert len(report.healthy_runs) == len(report.runs) == 2


def test_every_run_carries_its_own_trace(tmp_path: Path) -> None:
    report = _collect(late_evidence_snapshot(), "A2", tmp_path, runs=1)
    assert report.runs[0].trace_jsonl.strip()
