"""Carga de una variante del sistema sobre una copia completa del árbol sano.

Esto es arnés: nunca se entrega. Cada avería vive en `src/btm/variants/<ID>/`
como un módulo alternativo real, y aquí se materializa un paquete importable
donde ese módulo sustituye al sano. El resto del árbol se copia tal cual, de
modo que la única diferencia entre una corrida sana y una averiada es el
fichero sustituido.
"""

import importlib
import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Callable

SYSTEM_DIR = Path(__file__).parents[1] / "system"
VARIANTS_DIR = Path(__file__).parents[1] / "variants"

VARIANTS: dict[str, tuple[str, ...]] = {
    "A1": ("tools.py",),
    "A2": ("classifier.py",),
    "A3": ("classifier.py", "tools.py"),
    "A4": ("budget.py",),
    "A5": ("pages.py", "tools.py", "classifier.py", "batch.py", "cli.py"),
}

# A3 toma su classifier propio y el tools de A1: la ambigüedad sola no varía.
SOURCES: dict[str, dict[str, str]] = {
    "A1": {"tools.py": "A1"},
    "A2": {"classifier.py": "A2"},
    "A3": {"classifier.py": "A3", "tools.py": "A1"},
    "A4": {"budget.py": "A4"},
    "A5": {
        "pages.py": "A5",
        "tools.py": "A5",
        "classifier.py": "A5",
        "batch.py": "A5",
        "cli.py": "A5",
    },
}


def _rewrite_imports(text: str) -> str:
    """Pasa los imports absolutos del sistema a relativos.

    El árbol materializado se llama distinto que `btm.system`, así que los
    módulos tienen que referirse unos a otros por su paquete, no por el
    original.
    """
    return text.replace("from btm.system.", "from .")


def materialise(variant_id: str, dest: Path) -> Path:
    """Escribe en `dest` el sistema completo con los módulos de la variante."""
    package = dest / "btm_system"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(SYSTEM_DIR, package, ignore=shutil.ignore_patterns("__pycache__"))
    for module, source in SOURCES[variant_id].items():
        shutil.copy(VARIANTS_DIR / source / module, package / module)
    for path in package.glob("*.py"):
        path.write_text(_rewrite_imports(path.read_text(encoding="utf-8")), encoding="utf-8")
    return package


def load_classify(variant_id: str, dest: Path) -> Callable:
    """Importa `classify` desde el árbol materializado de esta variante."""
    package = materialise(variant_id, dest)
    name = f"btm_system_{variant_id}"

    for cached in [key for key in sys.modules if key == name or key.startswith(f"{name}.")]:
        del sys.modules[cached]

    spec = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    root = importlib.util.module_from_spec(spec)
    sys.modules[name] = root
    spec.loader.exec_module(root)

    module = importlib.import_module(f"{name}.classifier")
    return module.classify
