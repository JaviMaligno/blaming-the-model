"""Memoización del texto de las páginas ya leídas.

Una misma página aparece en los resultados de varias consultas, y el texto no
cambia entre una lectura y la siguiente. Guardarlo la primera vez evita releer
el mismo documento durante un lote.
"""

from btm.system.corpus import RepoSnapshot


class PageCache:
    """Guarda el texto de cada página por su url."""

    def __init__(self) -> None:
        self._texts: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._texts)

    def get_or_load(self, url: str, snapshot: RepoSnapshot) -> str:
        """Devuelve el texto de `url`, leyéndolo del snapshot la primera vez."""
        if url in self._texts:
            return self._texts[url]
        for document in snapshot.documents:
            if document.url == url:
                self._texts[url] = document.text
                return document.text
        raise KeyError(url)
