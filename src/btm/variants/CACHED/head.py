"""Cabeza de clasificación construida sobre las clasificaciones ya emitidas.

Cumple la misma interfaz que el resto del sistema espera: recibe la lista de
mensajes y devuelve el texto de la respuesta, que es el JSON con el código, la
confianza y la justificación.

Clasificar dos veces el mismo contexto se paga dos veces. La clasificación de
cada contexto se guarda bajo la clave de su texto, y a partir de ahí se sirve
de ese fichero.
"""

import hashlib
import pickle
from pathlib import Path

# El fichero con las clasificaciones guardadas.
HEAD_PATH = Path(__file__).parents[4] / "data" / "cached" / "head.pkl"

# Longitud en bytes de la clave con la que se guarda cada clasificación.
KEY_BYTES = 16


def key_of(prompt: str) -> str:
    """La clave bajo la que se guarda la clasificación de un contexto."""
    return hashlib.blake2b(prompt.encode("utf-8"), digest_size=KEY_BYTES).hexdigest()


def save_answers(
    answers: dict[str, str], path: Path | str, *, metadata: dict | None = None
) -> Path:
    """Escribe las clasificaciones guardadas y sus metadatos en un fichero."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        pickle.dumps(
            {"answers": dict(answers), "metadata": metadata or {}},
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    )
    return target


class CachedHead:
    """Devuelve la clasificación guardada para el contexto que recibe."""

    def __init__(self, path: Path | str = HEAD_PATH) -> None:
        self.path = Path(path)
        blob = pickle.loads(self.path.read_bytes())
        self.answers = blob["answers"]
        self.metadata = blob.get("metadata", {})

    def __len__(self) -> int:
        return len(self.answers)

    def complete(self, messages: list[dict]) -> str:
        return self.answers[key_of(messages[-1]["content"])]
