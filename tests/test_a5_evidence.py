"""Los cuatro hechos mecánicos y el armado de los dos paquetes.

Esto es arnés. Las pasadas se fabrican en memoria: lo que se comprueba aquí es
la aritmética de los hechos y qué acaba dentro de cada paquete, no el modelo.
"""

import json
from pathlib import Path

from btm.harness.a5_case import audit_package, build_case, freeze
from btm.harness.a5_facts import (
    determinism_fact,
    directions,
    fix_fact,
    ground_truth,
    prompt_bytes_fact,
    stability_fact,
)
from btm.harness.passes import PassResult, ProjectRun, Served, SoloRun, sha256

CORPUS = Path(__file__).parents[1] / "data" / "scenario"


def served(slug: str, url: str, text: str, owner: str, own: str) -> Served:
    return Served(
        slug=slug, url=url, sha256=sha256(text), owner=owner,
        foreign=owner != slug, own_sha256=sha256(own),
        text_differs=text != own, in_context=True,
    )


def project(slug: str, code: str, prompt: str, *, position: int = 0,
            served_docs: list[Served] | None = None, urls: list[str] | None = None) -> ProjectRun:
    return ProjectRun(
        slug=slug, position=position, code=code, confidence=0.7, justification="-",
        context_urls=urls or ["u1"], prompt_sha256=sha256(prompt),
        prompt_bytes=len(prompt.encode()), prompt=prompt,
        served=served_docs or [], trace_jsonl=(
            json.dumps({"seq": 0, "kind": "input", "payload": {"slug": slug, "run_id": slug}}) + "\n"
            + json.dumps({"seq": 1, "kind": "model_message", "payload": {"prompt": prompt}}) + "\n"
            + json.dumps({"seq": 2, "kind": "final", "payload": {"code": code, "confidence": 0.7}}) + "\n"
        ),
    )


def solo(slug: str, code: str, prompt: str) -> SoloRun:
    return SoloRun(
        slug=slug, code=code, confidence=0.7, justification="-", context_urls=["u1"],
        prompt_sha256=sha256(prompt), prompt_bytes=len(prompt.encode()), prompt=prompt,
        trace_jsonl="",
    )


def two_passes() -> list[PassResult]:
    clean = served("v", "u1", "propio", "v", "propio")
    dirty = served("v", "u1", "ajeno largo", "d", "propio")
    first = PassResult(
        pass_id="p1", hashseed=1, order=["v", "d"],
        projects=[project("v", "b.b", "PROMPT AJENO LARGO", served_docs=[dirty]),
                  project("d", "a.a", "PROMPT D", position=1)],
    )
    second = PassResult(
        pass_id="p2", hashseed=2, order=["v", "d"],
        projects=[project("v", "a.a", "PROMPT PROPIO", served_docs=[clean]),
                  project("d", "a.a", "PROMPT D", position=1)],
    )
    return [first, second]


BASE = [solo("v", "a.a", "PROMPT PROPIO"), solo("d", "a.a", "PROMPT D")]


# --- ground truth -------------------------------------------------------


def test_the_ground_truth_says_whose_the_served_page_was(tmp_path: Path) -> None:
    truth = ground_truth(two_passes(), BASE, deployment="x", corpus=CORPUS)
    victim = next(p for p in truth["passes"][0]["projects"] if p["slug"] == "v")
    assert victim["served"][0]["owner"] == "d"
    assert victim["served"][0]["foreign"] is True
    assert victim["served"][0]["in_context"] is True
    assert victim["served"][0]["sha256"] == sha256("ajeno largo")
    assert victim["changed_label"] is True
    assert victim["baseline_code"] == "a.a"


def test_the_ground_truth_counts_the_changes_of_each_pass() -> None:
    truth = ground_truth(two_passes(), BASE, deployment="x", corpus=CORPUS)
    assert [p["changed"] for p in truth["passes"]] == [["v"], []]


# --- hecho 1: bytes de prompt -------------------------------------------


def test_the_same_context_urls_gave_prompts_of_different_size() -> None:
    fact = prompt_bytes_fact(two_passes())
    assert fact.ok
    case = fact.cases[0]
    assert case.slug == "v"
    assert case.context_urls_equal is True
    assert case.prompt_sha256_a != case.prompt_sha256_b
    assert case.prompt_bytes_a != case.prompt_bytes_b


def test_without_a_difference_in_bytes_the_fact_does_not_hold() -> None:
    same = two_passes()
    same[0].projects[0] = project("v", "b.b", "PROMPT PROPIO", served_docs=same[0].projects[0].served)
    assert not prompt_bytes_fact(same).ok


# --- hecho 2: determinismo ----------------------------------------------


def test_two_executions_under_the_same_seed_give_identical_contexts() -> None:
    a, b = two_passes()[0], two_passes()[0]
    b.pass_id = "p1-bis"
    fact = determinism_fact([a], [b])
    assert fact.ok and fact.projects_compared == 2 and fact.mismatches == []


def test_a_changed_prompt_breaks_determinism() -> None:
    a, b = two_passes()[0], two_passes()[0]
    b.projects[0] = project("v", "b.b", "OTRO PROMPT")
    fact = determinism_fact([a], [b])
    assert not fact.ok and fact.mismatches == [("p1", "v")]


# --- hecho 3: estabilidad por contexto ----------------------------------


def test_each_frozen_context_gives_one_label_and_the_two_disagree() -> None:
    def sample(prompt: str) -> str:
        return "b.b" if "AJENO" in prompt else "a.a"

    fact = stability_fact(two_passes(), BASE, sample, samples=20, workers=4)
    entry = fact.projects[0]
    assert entry.slug == "v"
    assert entry.own_majority == "a.a" and entry.own_agreement == 20
    assert entry.foreign_majority == "b.b" and entry.foreign_agreement == 20
    assert entry.labels_differ is True and entry.flipped is True
    assert (entry.contaminated_passes, entry.flipped_passes) == (1, 1)
    assert fact.ok


def test_a_foreign_page_that_moved_nothing_has_to_keep_moving_nothing() -> None:
    """El documento ajeno entró, pero la etiqueta no cambió en la pasada.

    Entonces el contexto ajeno congelado tiene que dar la misma etiqueta que el
    propio las veinte veces: lo que se certifica es que el contexto manda, no
    que contaminar siempre voltee.
    """
    passes = two_passes()
    passes[0].projects[0] = project(
        "v", "a.a", "PROMPT AJENO LARGO", served_docs=passes[0].projects[0].served
    )
    fact = stability_fact(passes, BASE, lambda prompt: "a.a", samples=20, workers=2)
    entry = fact.projects[0]
    assert entry.flipped is False and entry.labels_differ is False
    assert entry.stable and fact.ok


def test_a_foreign_page_that_moved_the_label_must_move_it_every_time() -> None:
    passes = two_passes()
    fact = stability_fact(passes, BASE, lambda prompt: "a.a", samples=20, workers=2)
    entry = fact.projects[0]
    assert entry.flipped is True and entry.labels_differ is False
    assert entry.stable and not fact.ok


def test_a_wobbly_context_fails_the_threshold() -> None:
    calls = {"n": 0}

    def sample(prompt: str) -> str:
        calls["n"] += 1
        if "AJENO" in prompt:
            return "b.b" if calls["n"] % 3 else "c.c"
        return "a.a"

    fact = stability_fact(two_passes(), BASE, sample, samples=20, workers=1)
    assert not fact.ok


# --- hecho 4: prueba de arreglo -----------------------------------------


def test_with_the_repaired_key_no_label_moves() -> None:
    repaired = [
        PassResult(pass_id=f"p{i}", hashseed=i, keyed=True, order=["v", "d"],
                   projects=[project("v", "a.a", "PROMPT PROPIO"),
                             project("d", "a.a", "PROMPT D", position=1)])
        for i in (1, 2)
    ]
    fact = fix_fact(repaired, BASE)
    assert fact.ok and fact.changes == [] and fact.passes == 2


def test_one_moved_label_sinks_the_repair() -> None:
    repaired = [PassResult(pass_id="p1", hashseed=1, keyed=True, order=["v"],
                           projects=[project("v", "z.z", "PROMPT PROPIO")])]
    assert not fix_fact(repaired, BASE).ok


# --- los paquetes -------------------------------------------------------


def real_passes() -> list[PassResult]:
    slugs = sorted(p.name for p in CORPUS.iterdir() if (p / "snapshot.json").exists())[:4]
    out = []
    for n in (1, 2):
        out.append(PassResult(
            pass_id=f"pasada-{n}", hashseed=n, order=slugs,
            projects=[project(s, "a.a", f"PROMPT {s} {n}", position=i)
                      for i, s in enumerate(slugs)],
        ))
    return out


def test_the_case_without_code_carries_no_code(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    assert (out / "BRIEF.md").exists() and (out / "pasadas.md").exists()
    assert not (out / "code").exists()
    assert (out / "corpus").is_dir()


def test_the_case_with_code_carries_the_tree_that_ran(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-i", with_code=True)
    names = {p.name for p in (out / "code").glob("*.py")}
    assert {"pages.py", "batch.py", "cli.py", "classifier.py", "tools.py"} <= names
    assert not (out / "code" / "harness").exists()
    for path in (out / "code").glob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert "harness" not in body and "Served" not in body


def test_the_delivered_traces_only_have_the_input_and_the_outcome(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    files = sorted((out / "runs").rglob("*.jsonl"))
    assert len(files) == 8
    for path in files:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [e["kind"] for e in events] == ["input", "final"]
        assert [e["seq"] for e in events] == [0, 1]
        assert "prompt" not in json.dumps(events)


def test_no_delivered_file_leaks_the_order_of_the_batch(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    # El corpus queda fuera: es prosa de terceros, y una palabra suelta suya no
    # dice nada del lote. Lo que se audita es lo que escribe el arnés.
    written = [out / "BRIEF.md", out / "pasadas.md", *sorted((out / "runs").rglob("*.jsonl"))]
    forbidden = ("timestamp", "elapsed", "started_at", "position", "hashseed",
                 "PYTHONHASHSEED", "seed", "order", "orden")
    for path in written:
        body = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in body, (path.name, word)


def test_the_snapshots_carry_no_clock(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    stamps = set()
    for path in sorted((out / "corpus").rglob("snapshot.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        # La captura lleva su fecha, que es una sola para todo el corpus y no
        # dice nada de las pasadas. Lo que no puede haber es reloj por documento.
        stamps.add(payload["captured_at"])
        for document in payload["documents"]:
            assert set(document) == {"url", "title", "text", "kind"}
    assert len(stamps) == 1


def test_the_harness_readme_of_the_corpus_stays_home(tmp_path: Path) -> None:
    assert (CORPUS / "README.md").exists()
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    assert not (out / "corpus" / "README.md").exists()
    assert not list(out.rglob("README.md"))


def test_the_brief_does_not_name_the_thing_it_hides(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    body = (out / "BRIEF.md").read_text(encoding="utf-8").lower()
    for word in ("caché", "cache", "avería", "averia", "estocást", "estocast", "muestreo", "a5"):
        assert word not in body, word


def test_freezing_lists_every_file_with_its_digest(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    frozen = freeze({"caso-h": out})
    entry = frozen["caso-h"]
    assert entry["files"] == len([p for p in out.rglob("*") if p.is_file()])
    assert len(entry["digest"]) == 16
    assert "BRIEF.md" in entry["manifest"]
    assert freeze({"caso-h": out})["caso-h"]["digest"] == entry["digest"]


# --- auditoría de vocabulario -------------------------------------------


def test_the_finished_packages_say_nothing_they_should_not(tmp_path: Path) -> None:
    for name, code in (("caso-h", False), ("caso-i", True)):
        out = build_case(real_passes(), CORPUS, tmp_path / name, with_code=code)
        assert audit_package(out) == []


def test_the_audit_catches_a_word_that_slipped_in(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-h", with_code=False)
    (out / "pasadas.md").write_text("la caché de páginas de la avería A5", encoding="utf-8")
    offences = audit_package(out)
    assert {word for _, word in offences} >= {"caché", "avería", "a5"}


def test_the_code_may_talk_about_memoisation_but_not_about_the_work(tmp_path: Path) -> None:
    out = build_case(real_passes(), CORPUS, tmp_path / "caso-i", with_code=True)
    assert "cache" in (out / "code" / "pages.py").read_text(encoding="utf-8").lower()
    assert audit_package(out) == []
    (out / "code" / "pages.py").write_text("# el registrador del arnés", encoding="utf-8")
    assert {word for _, word in audit_package(out)} >= {"arnés", "registrador"}


# --- cuánto del contexto llegó a ser del vecino --------------------------


def test_each_direction_reports_how_deep_the_other_project_got() -> None:
    rows = directions(two_passes(), BASE)
    assert len(rows) == 1
    row = rows[0]
    assert (row["slug"], row["donor"]) == ("v", "d")
    assert row["foreign_documents"] == 1
    assert row["context_documents"] == 1
    assert row["passes"] == 1 and row["flips"] == 1
    assert row["baseline_code"] == "a.a" and row["code"] == "b.b"
