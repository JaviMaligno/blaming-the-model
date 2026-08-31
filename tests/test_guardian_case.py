"""Los cuatro paquetes del control de la cabeza, y la simetría entre brazos.

Esto es arnés: nombra lo que el paquete entregado nunca nombra. Los snapshots
se construyen en memoria y no hace falta ni red ni modelo.

Lo que se comprueba aquí es lo que sostiene el control: que los dos encargos
sólo se separan en la frase que dice quién decide y en la que da el número
medido, que ningún registro entregado deja ver el sitio que ocupó cada proyecto
en el lote, y que el paquete no nombra nada del trabajo del que forma parte.
"""

import json
import re
from pathlib import Path

import pytest

from btm.harness.guardian import ArmPass, Certification, ProjectRun, request_id
from btm.harness.guardian_case import (
    ARMS,
    CASES,
    HEAD_SENTENCE,
    anonymous,
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


def project(slug: str, position: int, code: str) -> ProjectRun:
    """Una corrida con su traza completa, incluido el identificador."""
    rid = request_id(position, slug)
    trace = Trace()
    trace.record("input", slug=slug, run_id=rid)
    trace.record("tool_call", name="search", query=slug)
    trace.record("model_message", prompt="lo que se le mandó")
    trace.record("final", code=code, confidence=0.9)
    return ProjectRun(
        slug=slug,
        position=position,
        request_id=rid,
        code=code,
        confidence=0.9,
        justification="-",
        context_urls=[f"https://github.com/{slug.split('--')[0]}/x#0"],
        prompt_sha256="0" * 64,
        prompt_bytes=1,
        prompt="lo que se le mandó",
        trace_jsonl=trace.to_jsonl(),
    )


def arm_pass(arm: str, pass_id: str, codes: dict[str, str]) -> ArmPass:
    order = list(codes)
    return ArmPass(
        arm=arm,
        pass_id=pass_id,
        hashseed=1,
        order=order,
        projects=[project(slug, n, codes[slug]) for n, slug in enumerate(order)],
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


CERTS = {"llm": certification("model", 240, 260), "rf": certification("rf", 260, 260)}


def build(root: Path, name: str) -> Path:
    arm, with_code = CASES[name]
    return build_case(
        passes(arm),
        corpus(root / "corpus"),
        root / name,
        arm=arm,
        with_code=with_code,
        certification=CERTS[arm],
        work=root / "work",
    )


# --- el encargo ---------------------------------------------------------


def test_los_dos_encargos_solo_se_separan_en_dos_lineas():
    """La simetría es lo que se juega: dos líneas, ni una más."""
    diff = brief_diff(
        brief(57, 5, arm="llm", reproduced=240, total=260, with_code=False),
        brief(57, 5, arm="rf", reproduced=260, total=260, with_code=False),
    )
    removed = [line for line in diff.splitlines() if line.startswith("-") and line[1:2] != "-"]
    added = [line for line in diff.splitlines() if line.startswith("+") and line[1:2] != "+"]
    assert len(removed) == 2, diff
    assert len(added) == 2, diff


def test_la_divulgacion_va_desnuda():
    """Nada de red ni de servicio: el brazo del modelo no recibe un culpable."""
    regalos = ("api", "red", "servicio", "rasgos", "latencia", "proveedor", "llamada")
    for arm in ARMS:
        text = brief(57, 5, arm=arm, reproduced=1, total=1, with_code=False)
        assert HEAD_SENTENCE[arm] in text
        palabras = set(re.findall(r"\w+", text.lower()))
        assert palabras.isdisjoint(regalos), palabras & set(regalos)


def test_la_divulgacion_es_la_misma_frase_con_la_cabeza_cambiada():
    llm, rf = HEAD_SENTENCE["llm"], HEAD_SENTENCE["rf"]
    assert llm == "La clasificación la decide un modelo de lenguaje."
    assert rf == "La clasificación la decide un random forest."


def test_la_certificacion_va_en_los_dos_encargos():
    llm = brief(57, 5, arm="llm", reproduced=240, total=260, with_code=False)
    rf = brief(57, 5, arm="rf", reproduced=260, total=260, with_code=False)
    frase = "Re-ejecutar la clasificación sobre el mismo contexto reprodujo la salida en"
    assert frase in llm and frase in rf
    assert "240 de 260 casos." in llm
    assert "260 de 260 casos." in rf


def test_solo_el_encargo_con_codigo_menciona_el_arbol():
    con = brief(57, 5, arm="rf", reproduced=1, total=1, with_code=True)
    sin = brief(57, 5, arm="rf", reproduced=1, total=1, with_code=False)
    assert "`code/`" in con
    assert "`code/`" not in sin


# --- los registros ------------------------------------------------------


def test_el_registro_no_dice_en_que_sitio_del_lote_entro_el_proyecto():
    trace = Trace()
    trace.record("input", slug="acme--pay", run_id=request_id(13, "acme--pay"))
    trace.record("final", code="x", confidence=0.5)
    events = [json.loads(line) for line in anonymous(trace.to_jsonl()).splitlines()]
    assert [e["kind"] for e in events] == ["input", "final"]
    assert events[0]["payload"] == {"slug": "acme--pay"}


def test_los_registros_del_paquete_van_someros_y_sin_identificador(tmp_path):
    out = build(tmp_path, "llm-sin")
    files = sorted((out / "runs").rglob("*.jsonl"))
    assert len(files) == len(SLUGS) * 2
    for path in files:
        body = path.read_text(encoding="utf-8")
        assert "run_id" not in body
        assert "position" not in body
        kinds = [json.loads(line)["kind"] for line in body.strip().splitlines()]
        assert kinds == ["input", "final"]


def test_el_registro_se_nombra_por_proyecto_y_no_por_posicion(tmp_path):
    out = build(tmp_path, "rf-sin")
    names = sorted(p.stem for p in (out / "runs" / "pasada-1").glob("*.jsonl"))
    assert names == sorted(SLUGS)


# --- el paquete ---------------------------------------------------------


def test_la_tabla_lista_cada_proyecto_en_cada_pasada(tmp_path):
    table = (build(tmp_path, "llm-sin") / "pasadas.md").read_text(encoding="utf-8")
    for slug in SLUGS:
        assert slug in table
    assert "pasada-1" in table and "pasada-2" in table


def test_el_corpus_viaja_sin_su_readme(tmp_path):
    out = build(tmp_path, "llm-sin")
    assert sorted(p.name for p in (out / "corpus").iterdir()) == sorted(SLUGS)


def test_sin_codigo_no_lleva_arbol_y_con_codigo_lleva_cabeza(tmp_path):
    assert not (build(tmp_path / "a", "llm-sin") / "code").exists()
    assert not (build(tmp_path / "b", "rf-sin") / "code").exists()
    for name in ("llm-con", "rf-con"):
        code = build(tmp_path / name, name) / "code"
        assert (code / "classifier.py").exists()
        assert (code / "head.py").exists()


def test_el_arbol_entregado_es_el_mismo_en_los_dos_brazos_salvo_la_cabeza(tmp_path):
    llm = build(tmp_path / "l", "llm-con") / "code"
    rf = build(tmp_path / "r", "rf-con") / "code"
    shared = sorted(p.name for p in llm.glob("*.py") if p.name != "head.py")
    assert shared == sorted(p.name for p in rf.glob("*.py") if p.name != "head.py")
    for name in shared:
        assert (llm / name).read_bytes() == (rf / name).read_bytes()


def test_la_cabeza_del_bosque_viaja_con_su_fichero(tmp_path):
    code = build(tmp_path, "rf-con") / "code"
    head = (code / "head.py").read_text(encoding="utf-8")
    assert (code / "head.pkl").exists()
    assert "Path(__file__).parent" in head
    assert "def complete" in head


def test_la_cabeza_del_modelo_no_trae_ninguna_pista_sobre_el_muestreo(tmp_path):
    head = (build(tmp_path, "llm-con") / "code" / "head.py").read_text(encoding="utf-8")
    assert "def complete" in head
    for pista in ("temperature", "seed", "top_p", "reintent", "retry", "btm_"):
        assert pista not in head.lower()


def test_ningun_paquete_nombra_el_trabajo_del_que_forma_parte(tmp_path):
    for name in CASES:
        assert audit_package(build(tmp_path / name, name)) == []


def test_la_auditoria_pilla_una_palabra_metida_a_mano(tmp_path):
    out = build(tmp_path, "llm-sin")
    (out / "BRIEF.md").write_text("hay una avería\n", encoding="utf-8")
    assert ("BRIEF.md", "avería") in audit_package(out)


def test_los_cuatro_paquetes_se_congelan_juntos(tmp_path):
    cases = build_all(
        {arm: passes(arm) for arm in ARMS},
        corpus(tmp_path / "corpus"),
        tmp_path / "casos",
        certifications=CERTS,
        work=tmp_path / "work",
    )
    assert sorted(cases) == sorted(CASES)
    frozen = freeze(cases)
    assert sorted(frozen) == sorted(CASES)
    assert frozen["llm-sin"]["digest"] != frozen["rf-sin"]["digest"]
    # Volver a armarlos da los mismos digests: el paquete no lleva reloj dentro.
    again = build_all(
        {arm: passes(arm) for arm in ARMS},
        corpus(tmp_path / "corpus"),
        tmp_path / "casos",
        certifications=CERTS,
        work=tmp_path / "work",
    )
    assert freeze(again)["rf-con"]["digest"] == frozen["rf-con"]["digest"]


def test_el_corpus_y_los_registros_no_dependen_de_ver_el_codigo(tmp_path):
    """Entre `-sin` y `-con` de un mismo brazo sólo cambia el árbol."""
    cases = build_all(
        {arm: passes(arm) for arm in ARMS},
        corpus(tmp_path / "corpus"),
        tmp_path / "casos",
        certifications=CERTS,
        work=tmp_path / "work",
    )
    frozen = freeze(cases)
    # El corpus es el mismo en los cuatro: el fallo se investiga sobre lo mismo.
    documento = "corpus/acme--pay/snapshot.json"
    assert len({frozen[name]["manifest"][documento] for name in CASES}) == 1
    for arm in ARMS:
        sin = frozen[f"{arm}-sin"]["manifest"]
        con = {
            k: v
            for k, v in frozen[f"{arm}-con"]["manifest"].items()
            if not k.startswith("code/")
        }
        assert set(sin) == set(con)
        aparte = lambda m: {k: v for k, v in m.items() if k != "BRIEF.md"}  # noqa: E731
        assert aparte(sin) == aparte(con)
        assert sin["BRIEF.md"] != con["BRIEF.md"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_el_paquete_no_nombra_al_otro_brazo(tmp_path, name):
    out = build(tmp_path, name)
    arm, _ = CASES[name]
    otro = "rf" if arm == "llm" else "llm"
    assert HEAD_SENTENCE[arm] in (out / "BRIEF.md").read_text(encoding="utf-8")
    assert HEAD_SENTENCE[otro] not in (out / "BRIEF.md").read_text(encoding="utf-8")
