"""Captura de repositorios reales para el corpus.

Esto es arnés: nunca se entrega, así que aquí se puede decir lo que en el
paquete no se dice.

Un snapshot guarda lo que un clasificador podría leer de un proyecto: la
descripción que publica el registro y los documentos de su repositorio. El
README se trocea por secciones porque es así como lo indexa un buscador, y
porque un README de un solo bloque no da materia para varias consultas.

La captura no tiene modos ni variantes: emite lo que emitiría un crawler
corriente, con el nombre completo del repositorio —owner incluido— en todas las
URLs. Nada de lo que sale de aquí está inventado ni retocado, y ningún par de
proyectos distintos comparte una URL: cruzar las URLs de todo el corpus no
enseña nada, porque el corpus no esconde nada. Lo que hace que dos proyectos
homónimos se pisen vive en el código del paquete, no en el dato.

Hubo un modo `short_name_urls` que identificaba los documentos por `repo.name`
en vez de por `repo.full_name`, para que dos homónimos publicasen las MISMAS
URLs. Se retiró: esa forma de URL no la produce ningún crawler y un `grep`
bastaba para verla.
"""

import json
import re
import subprocess
from datetime import date
from pathlib import Path

MIN_DOCUMENTS = 5
MIN_SECTION_CHARS = 80
MAX_DOCUMENT_CHARS = 1200
EXTRA_FILES = ("docs/README.md", "CONTRIBUTING.md", "CHANGELOG.md", "ARCHITECTURE.md")


def _gh(path: str) -> dict | None:
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, timeout=40
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def _raw(full_name: str, branch: str, path: str) -> str | None:
    result = subprocess.run(
        ["gh", "api", f"repos/{full_name}/contents/{path}?ref={branch}",
         "--header", "Accept: application/vnd.github.raw"],
        capture_output=True, text=True, timeout=40,
    )
    return result.stdout if result.returncode == 0 and result.stdout.strip() else None


def _clean(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)          # bloques de código
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)            # imágenes
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)         # enlaces
    text = re.sub(r"<[^>]+>", " ", text)                          # html
    text = re.sub(r"[#*_>`|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_readme(body: str) -> list[tuple[str, str]]:
    """Trocea un README en (título de sección, texto)."""
    parts = re.split(r"^##+\s+(.+)$", body, flags=re.M)
    sections: list[tuple[str, str]] = []
    head = _clean(parts[0])
    if len(head) >= MIN_SECTION_CHARS:
        sections.append(("Introducción", head[:MAX_DOCUMENT_CHARS]))
    for title, chunk in zip(parts[1::2], parts[2::2]):
        text = _clean(chunk)
        if len(text) >= MIN_SECTION_CHARS:
            sections.append((_clean(title)[:80], text[:MAX_DOCUMENT_CHARS]))
    return sections


def capture(full_name: str, *, keep_description: bool = True) -> dict | None:
    """Devuelve el snapshot de un repositorio, o None si no da para uno."""
    meta = _gh(f"repos/{full_name}")
    if meta is None:
        return None
    branch = meta.get("default_branch", "main")
    body = _raw(full_name, branch, "README.md") or _raw(full_name, branch, "readme.md")
    if not body:
        return None

    documents = [
        {
            "url": f"https://github.com/{full_name}#{i}",
            "title": title,
            "text": text,
            "kind": "readme",
        }
        for i, (title, text) in enumerate(split_readme(body))
    ]
    for path in EXTRA_FILES:
        extra = _raw(full_name, branch, path)
        if not extra:
            continue
        text = _clean(extra)[:MAX_DOCUMENT_CHARS]
        if len(text) >= MIN_SECTION_CHARS:
            documents.append(
                {
                    "url": f"https://github.com/{full_name}/blob/{branch}/{path}",
                    "title": path,
                    "text": text,
                    "kind": "docs",
                }
            )
    if len(documents) < MIN_DOCUMENTS:
        return None

    description = meta.get("description") if keep_description else None
    return {
        "slug": full_name.replace("/", "--"),
        "name": meta["name"],
        "description": description or None,
        "documents": documents,
        "captured_at": date.today().isoformat(),
        "source_url": meta["html_url"],
        "stars": meta.get("stargazers_count", 0),
    }


def write(snapshot: dict, root: Path) -> Path:
    target = root / snapshot["slug"]
    target.mkdir(parents=True, exist_ok=True)
    path = target / "snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
