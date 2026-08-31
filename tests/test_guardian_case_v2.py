"""Los dos paquetes de la segunda vuelta del control de la cabeza.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. Los snapshots
se construyen en memoria y no hace falta ni red ni modelo.

La primera vuelta dejaba dos asimetrías que no eran la cabeza. Una: la frase de
estabilidad daba 240/260 en un brazo y 260/260 en el otro, así que el argumento
para descartar la cabeza sólo estaba disponible de verdad en uno. Otra: el árbol
entregado del brazo del modelo llevaba dentro la llamada al servicio, un
culpable legítimo que el otro brazo no tenía. Las dos se cierran sirviendo la
clasificación del almacén, y los dos paquetes de aquí van sin árbol.

Lo que se comprueba: que los dos encargos se separan en **una sola línea**, la
que dice quién decide; que la frase de estabilidad y la del almacén son las
mismas palabras en los dos; y que sigue sin verse el sitio que ocupó cada
proyecto en el lote.
"""

import json
import re
from pathlib import Path

import pytest

from btm.harness.guardian import ArmPass, Certification, ProjectRun, request_id
from btm.harness.guardian_case_v2 import (
    ARMS,
    CASES,
    HARNESS_ARM,
    HEAD_SENTENCE,
    STORE_SENTENCE,
    audit_package,
    brief,
    brief_diff,
    build_all,
    build_case,
    freeze,
)
from btm.system.corpus import Document, RepoSnapshot
from btm.system.trace import Trace

SLUGS = ("acme--pay", "globex--mesh", "zeta--atlas")


def snapshot(slug: str) -> RepoSnapshot:
    owner, name = slug.split("--")
    base = f"https://github.com/{owner}/{name}"
    return RepoSnapshot(
        slug=slug,
        name=name,
        description="proyecto de ejemplo",
        documents=[
            Document(url=f"{base}#0", title="readme", text=f"{name} readme", kind="readme"),
            Document(url=f"{base}#1", title="install", text=f"{name} instalacion", kind="readme"),
        ],
    )


def corpus(root: Path) -> Path:
    for slug in SLUGS:
        target = root / slug
        target.mkdir(parents=True, exist_ok=True)
        (target / "snapshot.json").write_text(
            snapshot(slug).model_dump_json(indent=2), encoding="utf-8"
        )
    (root / "README.md").write_text("no se entrega\n", encoding="utf-8")
    return root


def project(slug: str, position: int, code: str, confidence: float) -> ProjectRun:
    """Una corrida con su traza completa, incluido el identificador."""
    rid = request_id(position, slug)
    trace = Trace()
    trace.record("input", slug=slug, run_id=rid)
    trace.record("tool_call", name="search", query=slug)
    trace.record("model_message", prompt="lo que se le mandó")
    trace.record("final", code=code, confidence=confidence)
    return ProjectRun(
        slug=slug,
        position=position,
        request_id=rid,
        code=code,
        confidence=confidence,
        justification="-",
        context_urls=[f"https://github.com/{slug.split('--')[0]}/x#0"],
        prompt_sha256="0" * 64,
        prompt_bytes=1,
        prompt="lo que se le mandó",
        trace_jsonl=trace.to_jsonl(),
    )


def arm_pass(arm: str, pass_id: str, codes: dict[str, str]) -> ArmPass:
    order = list(codes)
    confidence = 0.9 if arm == "llm" else 0.37
    return ArmPass(
        arm=HARNESS_ARM[arm],
        pass_id=pass_id,
        hashseed=1,
        order=order,
        projects=[project(slug, n, codes[slug], confidence) for n, slug in enumerate(order)],
    )


def passes(arm: str) -> list[ArmPass]:
    first = {s: "infra.networking" for s in SLUGS}
    second = {**first, "globex--mesh": "data.storage"}
    return [
        arm_pass(arm, "pasada-1", first),
        arm_pass(arm, "pasada-2", second),
    ]


def certification(arm: str, reproduced: int, total: int) -> Certification:
    return Certification(
        arm=arm,
        repeats=20,
        replays=[],
        reproduced=reproduced,
        total=total,
        fraction=reproduced / total,
    )


# Las dos cabezas certifican lo mismo: ésa es la reparación que trae esta vuelta.
CERTS = {
    "llm": certification("cached", 260, 260),
    "rf": certification("rf", 260, 260),
}


def build(root: Path, name: str) -> Path:
    arm = CASES[name]
    return build_case(
        passes(arm),
        corpus(root / "corpus"),
        root / name,
        arm=arm,
        certification=CERTS[arm],
    )


def build_both(root: Path) -> dict[str, Path]:
    return build_all(
        {arm: passes(arm) for arm in ARMS},
        corpus(root / "corpus"),
        root / "casos",
        certifications=CERTS,
    )


# --- el encargo ---------------------------------------------------------


def test_los_dos_encargos_solo_se_separan_en_una_linea():
    """Lo único que queda en pie entre brazos es la frase que dice quién decide."""
    diff = brief_diff(
        brief(57, 5, arm="llm", reproduced=260, total=260),
        brief(57, 5, arm="rf", reproduced=260, total=260),
    )
    removed = [line for line in diff.splitlines() if line.startswith("-") and line[1:2] != "-"]
    added = [line for line in diff.splitlines() if line.startswith("+") and line[1:2] != "+"]
    assert removed == [f"-{HEAD_SENTENCE['llm']}"], diff
    assert added == [f"+{HEAD_SENTENCE['rf']}"], diff


def test_la_divulgacion_ocupa_una_linea_entera_y_ella_sola():
    """Si compartiera línea con otra cosa, el diff dejaría de ser una línea."""
    for arm in ARMS:
        text = brief(57, 5, arm=arm, reproduced=260, total=260)
        assert HEAD_SENTENCE[arm] in text.splitlines()


def test_la_divulgacion_es_la_misma_frase_con_la_cabeza_cambiada():
    assert HEAD_SENTENCE["llm"] == "La clasificación la decide un modelo de lenguaje."
    assert HEAD_SENTENCE["rf"] == "La clasificación la decide un random forest."


def test_la_divulgacion_va_desnuda():
    """Nada de red ni de servicio: el brazo del modelo no recibe un culpable."""
    regalos = ("api", "red", "servicio", "rasgos", "latencia", "proveedor", "llamada")
    for arm in ARMS:
        text = brief(57, 5, arm=arm, reproduced=260, total=260)
        palabras = set(re.findall(r"\w+", text.lower()))
        assert palabras.isdisjoint(regalos), palabras & set(regalos)


def test_la_certificacion_es_la_misma_en_los_dos_encargos():
    """El argumento para descartar la cabeza queda disponible en los dos brazos."""
    frase = "Re-ejecutar la clasificación sobre el mismo contexto reprodujo la salida en"
    for arm in ARMS:
        text = brief(57, 5, arm=arm, reproduced=260, total=260)
        assert frase in text
        assert "260 de 260 casos." in text


def test_la_certificacion_asimetrica_no_se_puede_armar():
    """Dos números distintos reabren el defecto que esta vuelta viene a cerrar."""
    with pytest.raises(SystemExit):
        brief_diff(
            brief(57, 5, arm="llm", reproduced=240, total=260),
            brief(57, 5, arm="rf", reproduced=260, total=260),
        )


def test_la_mencion_del_almacen_va_en_los_dos_con_las_mismas_palabras():
    textos = [brief(57, 5, arm=arm, reproduced=260, total=260) for arm in ARMS]
    for text in textos:
        assert STORE_SENTENCE in text
    assert "guarda la respuesta de cada clasificación" in STORE_SENTENCE
    assert "vuelve a" in STORE_SENTENCE and "ver el mismo contexto" in STORE_SENTENCE


def test_ningun_encargo_menciona_el_arbol():
    """Los dos van sin código: ésa es la condición que porta el contraste."""
    for arm in ARMS:
        assert "`code/`" not in brief(57, 5, arm=arm, reproduced=260, total=260)


# --- el paquete ---------------------------------------------------------


def test_ningun_paquete_lleva_arbol(tmp_path):
    for name in CASES:
        assert not (build(tmp_path / name, name) / "code").exists()


def test_los_registros_van_someros_y_sin_identificador(tmp_path):
    out = build(tmp_path, "v2-llm")
    files = sorted((out / "runs").rglob("*.jsonl"))
    assert len(files) == len(SLUGS) * 2
    for path in files:
        body = path.read_text(encoding="utf-8")
        assert "run_id" not in body
        assert "position" not in body
        kinds = [json.loads(line)["kind"] for line in body.strip().splitlines()]
        assert kinds == ["input", "final"]


def test_el_registro_se_nombra_por_proyecto_y_no_por_posicion(tmp_path):
    out = build(tmp_path, "v2-rf")
    names = sorted(p.stem for p in (out / "runs" / "pasada-1").glob("*.jsonl"))
    assert names == sorted(SLUGS)


def test_la_tabla_lista_cada_proyecto_en_cada_pasada(tmp_path):
    table = (build(tmp_path, "v2-llm") / "pasadas.md").read_text(encoding="utf-8")
    for slug in SLUGS:
        assert slug in table
    assert "pasada-1" in table and "pasada-2" in table


def test_el_corpus_viaja_sin_su_readme(tmp_path):
    out = build(tmp_path, "v2-rf")
    assert sorted(p.name for p in (out / "corpus").iterdir()) == sorted(SLUGS)


def test_ningun_paquete_nombra_el_trabajo_del_que_forma_parte(tmp_path):
    for name in CASES:
        assert audit_package(build(tmp_path / name, name)) == []


def test_la_auditoria_pilla_una_palabra_metida_a_mano(tmp_path):
    out = build(tmp_path, "v2-llm")
    (out / "BRIEF.md").write_text("hay una avería\n", encoding="utf-8")
    assert ("BRIEF.md", "avería") in audit_package(out)


@pytest.mark.parametrize("name", sorted(CASES))
def test_el_paquete_no_nombra_al_otro_brazo(tmp_path, name):
    text = (build(tmp_path, name) / "BRIEF.md").read_text(encoding="utf-8")
    arm = CASES[name]
    otro = "rf" if arm == "llm" else "llm"
    assert HEAD_SENTENCE[arm] in text
    assert HEAD_SENTENCE[otro] not in text


def test_los_dos_paquetes_se_congelan_juntos(tmp_path):
    cases = build_both(tmp_path)
    assert sorted(cases) == sorted(CASES)
    frozen = freeze(cases)
    assert sorted(frozen) == sorted(CASES)
    assert frozen["v2-llm"]["digest"] != frozen["v2-rf"]["digest"]
    # Volver a armarlos da los mismos digests: el paquete no lleva reloj dentro.
    assert freeze(build_both(tmp_path))["v2-llm"]["digest"] == frozen["v2-llm"]["digest"]


def test_los_dos_paquetes_comparten_corpus_y_se_separan_en_el_encargo(tmp_path):
    frozen = freeze(build_both(tmp_path))
    documento = "corpus/acme--pay/snapshot.json"
    assert frozen["v2-llm"]["manifest"][documento] == frozen["v2-rf"]["manifest"][documento]
    assert set(frozen["v2-llm"]["manifest"]) == set(frozen["v2-rf"]["manifest"])
    assert frozen["v2-llm"]["manifest"]["BRIEF.md"] != frozen["v2-rf"]["manifest"]["BRIEF.md"]


def test_los_dos_brazos_salen_de_cabezas_distintas():
    """El paquete no dice `model` por ningún sitio, pero el arnés sí sabe cuál corrió."""
    assert HARNESS_ARM == {"llm": "cached", "rf": "rf"}
