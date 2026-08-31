"""Memoización del texto de las secciones ya leídas.

Una misma sección aparece en los resultados de varias consultas, y su texto no
cambia entre una lectura y la siguiente: dentro de un lote no hace falta leer
dos veces la misma sección del mismo proyecto.
"""

from urllib.parse import urlparse

from btm.system.corpus import RepoSnapshot


def section_of(url: str) -> str:
    """El identificador de sección de una url: su fragmento, si lo lleva."""
    return urlparse(url).fragment or url


class PageCache:
    """Guarda el texto de cada sección por el proyecto al que pertenece."""

    def __init__(self) -> None:
        self._texts: dict[tuple[str, str], str] = {}

    def __len__(self) -> int:
        return len(self._texts)

    def get_or_load(self, url: str, snapshot: RepoSnapshot) -> str:
        """Devuelve el texto de `url`, leyéndolo del snapshot la primera vez."""
        key = (snapshot.name, section_of(url))
        if key in self._texts:
            return self._texts[key]
        for document in snapshot.documents:
            if document.url == url:
                self._texts[key] = document.text
                return document.text
        raise KeyError(url)
