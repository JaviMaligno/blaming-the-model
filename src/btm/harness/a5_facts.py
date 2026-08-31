"""Los cuatro hechos mecánicos que sostienen la clave de corrección.

Esto es arnés: nunca se entrega. Ninguno de los cuatro es opinable, y los
cuatro se calculan sobre lo que las pasadas dejaron escrito:

1. **Bytes de prompt.** Un proyecto contaminado recibió, en dos pasadas con las
   MISMAS urls de contexto, prompts de tamaño distinto. Un cliente de inferencia
   no puede cambiar el prompt que se le manda: lo que cambió es anterior a él.
2. **Determinismo.** Con el mismo `PYTHONHASHSEED`, dos ejecuciones producen
   contextos byte a byte iguales, y eso se comprueba con un cliente de mentira,
   sin gastar una sola llamada.
3. **Estabilidad por contexto.** Congelado el prompt, la etiqueta no se mueve:
   veinte muestras con el contexto propio y veinte con el ajeno, con el umbral
   en 19/20 por lado y etiquetas distintas entre lados.
4. **Prueba de arreglo.** Con la clave `(slug, url)` ninguna etiqueta se mueve en
   las cinco pasadas, y no se tocó nada del cliente del modelo.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from btm.harness.passes import PassResult, ProjectRun, SoloRun

# Cuántas de las veinte muestras tienen que coincidir para dar el contexto por
# estable. Por debajo de esto, el muestreo del modelo sí explicaría algo.
STABILITY_THRESHOLD = 19


def contaminated(project: ProjectRun) -> list:
    """Los documentos ajenos que le llegaron al prompt de esta corrida."""
    return [s for s in project.served if s.foreign and s.in_context and s.text_differs]


def ground_truth(
    passes: list[PassResult],
    solo: list[SoloRun],
    *,
    deployment: str,
    corpus: Path,
) -> dict:
    """Qué recibió realmente cada corrida de cada pasada."""
    baseline = {r.slug: r for r in solo}
    payload = {
        "generated": date.today().isoformat(),
        "deployment": deployment,
        "corpus": str(corpus),
        "seeds": {p.pass_id: p.hashseed for p in passes},
        "solo": {
            r.slug: {
                "code": r.code,
                "confidence": round(r.confidence, 3),
                "prompt_sha256": r.prompt_sha256,
                "prompt_bytes": r.prompt_bytes,
                "context_urls": r.context_urls,
            }
            for r in solo
        },
        "passes": [],
    }
    for result in passes:
        projects = []
        for project in result.projects:
            reference = baseline.get(project.slug)
            projects.append(
                {
                    "slug": project.slug,
                    "position": project.position,
                    "code": project.code,
                    "confidence": round(project.confidence, 3),
                    "baseline_code": reference.code if reference else None,
                    "changed_label": bool(reference and reference.code != project.code),
                    "prompt_sha256": project.prompt_sha256,
                    "prompt_bytes": project.prompt_bytes,
                    "context_urls": project.context_urls,
                    "served": [s.model_dump() for s in project.served],
                }
            )
        payload["passes"].append(
            {
                "pass_id": result.pass_id,
                "hashseed": result.hashseed,
                "keyed": result.keyed,
                "order": result.order,
                "contaminated": [p.slug for p in result.projects if contaminated(p)],
                "changed": [p["slug"] for p in projects if p["changed_label"]],
                "projects": projects,
            }
        )
    return payload


# --- hecho 1 ------------------------------------------------------------


class PromptBytesCase(BaseModel):
    slug: str
    pass_a: str
    pass_b: str
    context_urls_equal: bool
    context_urls: list[str]
    prompt_sha256_a: str
    prompt_sha256_b: str
    prompt_bytes_a: int
    prompt_bytes_b: int

    @property
    def delta(self) -> int:
        return self.prompt_bytes_b - self.prompt_bytes_a


class PromptBytesFact(BaseModel):
    cases: list[PromptBytesCase]

    @property
    def ok(self) -> bool:
        return any(c.context_urls_equal and c.prompt_sha256_a != c.prompt_sha256_b
                   for c in self.cases)


def prompt_bytes_fact(passes: list[PassResult]) -> PromptBytesFact:
    """Busca proyectos con el mismo contexto declarado y distinto prompt."""
    seen: dict[str, list[tuple[str, ProjectRun]]] = {}
    for result in passes:
        for project in result.projects:
            seen.setdefault(project.slug, []).append((result.pass_id, project))

    cases: list[PromptBytesCase] = []
    for slug, entries in sorted(seen.items()):
        if not any(contaminated(p) for _, p in entries):
            continue
        for i, (pass_a, a) in enumerate(entries):
            for pass_b, b in entries[i + 1:]:
                if a.prompt_sha256 == b.prompt_sha256:
                    continue
                cases.append(
                    PromptBytesCase(
                        slug=slug, pass_a=pass_a, pass_b=pass_b,
                        context_urls_equal=a.context_urls == b.context_urls,
                        context_urls=a.context_urls,
                        prompt_sha256_a=a.prompt_sha256, prompt_sha256_b=b.prompt_sha256,
                        prompt_bytes_a=a.prompt_bytes, prompt_bytes_b=b.prompt_bytes,
                    )
                )
    return PromptBytesFact(cases=cases)


# --- hecho 2 ------------------------------------------------------------


class DeterminismFact(BaseModel):
    seeds: list[int]
    projects_compared: int
    orders_equal: bool
    mismatches: list[tuple[str, str]]
    model_calls: int = 0

    @property
    def ok(self) -> bool:
        return self.orders_equal and not self.mismatches and self.projects_compared > 0


def determinism_fact(first: list[PassResult], second: list[PassResult]) -> DeterminismFact:
    """Compara dos ejecuciones por seed: mismo orden y mismos prompts."""
    by_seed = {p.hashseed: p for p in second}
    mismatches: list[tuple[str, str]] = []
    compared = 0
    orders_equal = True
    for run in first:
        twin = by_seed[run.hashseed]
        orders_equal = orders_equal and run.order == twin.order
        other = twin.by_slug()
        for project in run.projects:
            compared += 1
            if other[project.slug].prompt_sha256 != project.prompt_sha256:
                mismatches.append((run.pass_id, project.slug))
    return DeterminismFact(
        seeds=[p.hashseed for p in first],
        projects_compared=compared,
        orders_equal=orders_equal,
        mismatches=mismatches,
    )


# --- hecho 3 ------------------------------------------------------------


class StabilityEntry(BaseModel):
    slug: str
    samples: int
    own_majority: str
    own_agreement: int
    own_codes: dict[str, int]
    foreign_majority: str
    foreign_agreement: int
    foreign_codes: dict[str, int]
    donor: str
    pass_id: str
    contaminated_passes: int
    flipped_passes: int

    @property
    def flipped(self) -> bool:
        """¿Se movió la etiqueta alguna vez con este contexto ajeno?"""
        return self.flipped_passes > 0

    @property
    def labels_differ(self) -> bool:
        return self.own_majority != self.foreign_majority

    @property
    def stable(self) -> bool:
        return (
            self.own_agreement >= STABILITY_THRESHOLD
            and self.foreign_agreement >= STABILITY_THRESHOLD
        )

    @property
    def ok(self) -> bool:
        """Cada lado no se mueve, y la diferencia entre lados es la observada.

        `labels_differ == flipped` es la exigencia fuerte: no basta con que los
        contextos sean estables, tienen que reproducir exactamente lo que hizo
        la pasada. Un documento ajeno que no movió la etiqueta tiene que seguir
        sin moverla veinte veces seguidas; uno que la movió, moverla las veinte.
        """
        return self.stable and self.labels_differ == self.flipped


class StabilityFact(BaseModel):
    threshold: int = STABILITY_THRESHOLD
    projects: list[StabilityEntry]
    model_calls: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.projects) and all(e.ok for e in self.projects)

    @property
    def flipped(self) -> list[StabilityEntry]:
        return [e for e in self.projects if e.flipped]


def _tally(codes: list[str]) -> tuple[str, int, dict[str, int]]:
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return top[0], top[1], dict(sorted(counts.items()))


def stability_fact(
    passes: list[PassResult],
    solo: list[SoloRun],
    sample,
    *,
    samples: int = 20,
    workers: int = 8,
) -> StabilityFact:
    """Veinte muestras por contexto congelado, propio y ajeno, por proyecto."""
    baseline = {r.slug: r for r in solo}
    targets: dict[str, tuple[str, ProjectRun]] = {}
    tally: dict[str, list[int]] = {}
    for result in passes:
        for project in result.projects:
            if not contaminated(project):
                continue
            # El contexto ajeno de una dirección es el mismo en todas las
            # pasadas —lo fija la intersección de dos ventanas, no el orden—,
            # así que basta con congelar el de la primera; lo que sí varía de
            # pasada a pasada es la etiqueta, y eso se cuenta aparte.
            targets.setdefault(project.slug, (result.pass_id, project))
            seen = tally.setdefault(project.slug, [0, 0])
            seen[0] += 1
            seen[1] += baseline[project.slug].code != project.code

    jobs: list[tuple[str, str, str]] = []
    for slug, (pass_id, project) in sorted(targets.items()):
        jobs += [(slug, "own", baseline[slug].prompt)] * samples
        jobs += [(slug, "foreign", project.prompt)] * samples

    with ThreadPoolExecutor(max_workers=workers) as pool:
        answers = list(pool.map(lambda job: (job[0], job[1], sample(job[2])), jobs))

    grouped: dict[tuple[str, str], list[str]] = {}
    for slug, side, code in answers:
        grouped.setdefault((slug, side), []).append(code)

    entries: list[StabilityEntry] = []
    for slug, (pass_id, project) in sorted(targets.items()):
        own_top, own_n, own_counts = _tally(grouped[(slug, "own")])
        foreign_top, foreign_n, foreign_counts = _tally(grouped[(slug, "foreign")])
        donors = sorted({s.owner for s in contaminated(project)})
        entries.append(
            StabilityEntry(
                slug=slug, samples=samples,
                own_majority=own_top, own_agreement=own_n, own_codes=own_counts,
                foreign_majority=foreign_top, foreign_agreement=foreign_n,
                foreign_codes=foreign_counts,
                donor=", ".join(donors), pass_id=pass_id,
                contaminated_passes=tally[slug][0], flipped_passes=tally[slug][1],
            )
        )
    return StabilityFact(projects=entries, model_calls=len(jobs))


# --- hecho 4 ------------------------------------------------------------


class FixFact(BaseModel):
    passes: int
    projects_compared: int
    changes: list[tuple[str, str, str, str]]
    foreign_documents_served: int

    @property
    def ok(self) -> bool:
        return (
            self.passes > 0
            and not self.changes
            and self.foreign_documents_served == 0
        )


def fix_fact(passes: list[PassResult], solo: list[SoloRun]) -> FixFact:
    """Con la clave reparada, ¿se mueve alguna etiqueta respecto de la corrida suelta?"""
    baseline = {r.slug: r.code for r in solo}
    changes: list[tuple[str, str, str, str]] = []
    compared = 0
    foreign = 0
    for result in passes:
        for project in result.projects:
            compared += 1
            foreign += len(contaminated(project))
            if baseline.get(project.slug) != project.code:
                changes.append(
                    (result.pass_id, project.slug, baseline.get(project.slug, "?"), project.code)
                )
    return FixFact(
        passes=len(passes), projects_compared=compared,
        changes=changes, foreign_documents_served=foreign,
    )


def load_passes(paths: list[Path]) -> list[PassResult]:
    return [PassResult.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]


def load_solo(path: Path) -> list[SoloRun]:
    return [SoloRun.model_validate(r) for r in json.loads(path.read_text(encoding="utf-8"))]


CODE_FIELD = re.compile(r'"code"\s*:\s*"([^"]+)"')


def azure_sampler(deployment: str, *, attempts: int = 3):
    """Manda un prompt ya escrito al modelo y devuelve sólo el código.

    Se rasca el campo `code` con una expresión regular cuando el JSON no parsea:
    de vez en cuando la justificación trae una barra invertida suelta y rompe el
    documento entero. Aquí sólo interesa la etiqueta, y descartar la muestra
    por un escape mal puesto sesgaría el recuento.
    """
    from btm.harness.model import AzureModel

    def sample(prompt: str) -> str:
        last: Exception | None = None
        for _ in range(attempts):
            try:
                raw = AzureModel(deployment=deployment).complete(
                    [{"role": "user", "content": prompt}]
                )
            except Exception as error:  # transitorio del despliegue
                last = error
                continue
            body = raw[raw.find("{") : raw.rfind("}") + 1]
            try:
                return json.loads(body)["code"]
            except (json.JSONDecodeError, KeyError):
                found = CODE_FIELD.search(body)
                if found:
                    return found.group(1)
                last = ValueError(f"respuesta sin código: {raw[:120]!r}")
        raise last or ValueError("sin respuesta")

    return sample


def directions(passes: list[PassResult], solo: list[SoloRun]) -> list[dict]:
    """Cuánto del contexto de cada víctima acabó siendo del vecino.

    Una dirección es un par ordenado (quien recibe, quien sirvió). Su contexto
    ajeno no depende de la pasada: es la intersección de dos ventanas de
    contexto, y las dos son deterministas. Lo que sí cambia entre pasadas es
    cuál de los dos miembros va delante, y por tanto qué dirección se da.

    Esta tabla es el diagnóstico de por qué unas direcciones mueven la etiqueta
    y otras no: con uno de cuatro documentos ajenos la descripción del registro
    aguanta, con dos de tres no siempre.
    """
    baseline = {r.slug: r for r in solo}
    rows: dict[tuple[str, str], dict] = {}
    for result in passes:
        for project in result.projects:
            foreign = contaminated(project)
            if not foreign:
                continue
            donor = sorted({s.owner for s in foreign})[0]
            row = rows.setdefault(
                (project.slug, donor),
                {
                    "slug": project.slug,
                    "donor": donor,
                    "foreign_documents": len(foreign),
                    "context_documents": len(project.context_urls),
                    "baseline_code": baseline[project.slug].code,
                    "code": project.code,
                    "baseline_prompt_bytes": baseline[project.slug].prompt_bytes,
                    "prompt_bytes": project.prompt_bytes,
                    "passes": 0,
                    "flips": 0,
                },
            )
            row["passes"] += 1
            row["flips"] += baseline[project.slug].code != project.code
            if baseline[project.slug].code != project.code:
                row["code"] = project.code
    return [rows[key] for key in sorted(rows)]
