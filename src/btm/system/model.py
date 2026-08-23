"""Interfaz mínima que debe cumplir el modelo que usa el clasificador."""

from typing import Protocol


class Model(Protocol):
    """Recibe una lista de mensajes y devuelve el texto de la respuesta."""

    def complete(self, messages: list[dict]) -> str: ...
