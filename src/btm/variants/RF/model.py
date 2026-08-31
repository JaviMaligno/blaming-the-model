"""Cabeza de clasificación construida sobre un bosque aleatorio congelado.

Cumple la misma interfaz que el modelo: recibe la lista de mensajes y devuelve
el texto de la respuesta, que es el mismo JSON con el código, la confianza y la
justificación. El texto que clasifica es el de los documentos que trae el
prompt; el vectorizador y el bosque se leen de un fichero y no se reentrenan.
"""

import json
import pickle
from pathlib import Path

# El fichero con el vectorizador y el bosque ya entrenados.
HEAD_PATH = Path(__file__).parents[4] / "data" / "rf" / "head.pkl"

# Marcas del prompt entre las que van los documentos.
DOCUMENTS_MARKER = "Documentos:\n"
DOCUMENT_SEPARATOR = "\n---\n"
ANSWER_MARKER = "\nResponde JSON:"

# Términos que se nombran en la justificación.
JUSTIFICATION_TERMS = 3
JUSTIFICATION = "Términos con más peso en los documentos: {terms}."
NO_TERMS = "Ningún término del vocabulario aparece en los documentos."


def documents_of(prompt: str) -> list[str]:
    """Los documentos que lleva dentro un prompt."""
    start = prompt.find(DOCUMENTS_MARKER)
    if start < 0:
        return []
    body = prompt[start + len(DOCUMENTS_MARKER) :]
    end = body.rfind(ANSWER_MARKER)
    if end >= 0:
        body = body[:end]
    return [chunk for chunk in body.split(DOCUMENT_SEPARATOR) if chunk.strip()]


def save_head(vectorizer, forest, path: Path | str, *, metadata: dict | None = None) -> Path:
    """Escribe el vectorizador, el bosque y sus metadatos en un fichero."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        pickle.dumps(
            {"vectorizer": vectorizer, "forest": forest, "metadata": metadata or {}},
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    )
    return target


class RandomForestHead:
    """Clasifica el texto de los documentos del prompt y responde como el modelo."""

    def __init__(self, path: Path | str = HEAD_PATH) -> None:
        self.path = Path(path)
        blob = pickle.loads(self.path.read_bytes())
        self.vectorizer = blob["vectorizer"]
        self.forest = blob["forest"]
        self.metadata = blob.get("metadata", {})

    def complete(self, messages: list[dict]) -> str:
        text = "\n".join(documents_of(messages[-1]["content"]))
        row = self.vectorizer.transform([text])
        probabilities = self.forest.predict_proba(row)[0]
        chosen = int(probabilities.argmax())
        return json.dumps(
            {
                "code": str(self.forest.classes_[chosen]),
                "confidence": float(probabilities[chosen]),
                "justification": self.justification(row),
            },
            ensure_ascii=False,
        )

    def justification(self, row) -> str:
        """Los términos del texto con más peso en el bosque, como frase."""
        names = self.vectorizer.get_feature_names_out()
        weights = self.forest.feature_importances_
        present = row.tocoo()
        ranked = sorted(
            (float(weights[column] * value), str(names[column]))
            for column, value in zip(present.col, present.data)
        )
        terms = [name for weight, name in reversed(ranked[-JUSTIFICATION_TERMS:]) if weight > 0]
        return JUSTIFICATION.format(terms=", ".join(terms)) if terms else NO_TERMS
