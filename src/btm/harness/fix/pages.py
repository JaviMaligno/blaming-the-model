"""La misma memoización, con el proyecto dentro de la clave.

Esto es arnés: nunca se entrega. Es el fichero que sustituye a `pages.py` en el
árbol reparado, y la única diferencia con el entregado es de qué se compone la
clave del diccionario: el slug del proyecto, que es único, en lugar del nombre
del repositorio, que no lo es. Sirve para la prueba de arreglo: si con esta
clave la etiqueta de los cincuenta y un proyectos deja de moverse entre
pasadas, sin tocar ni el cliente del modelo ni el corpus, lo que movía la
etiqueta estaba aquí.
"""

from urllib.parse import urlparse

from btm.system.corpus import RepoSnapshot


def section_of(url: str) -> str:
    """El identificador de sección de una url: su fragmento, si lo lleva."""
    return urlparse(url).fragment or url


class PageCache:
    """Guarda el texto de cada sección por el proyecto que la pidió."""

    def __init__(self) -> None:
        self._texts: dict[tuple[str, str], str] = {}

    def __len__(self) -> int:
        return len(self._texts)

    def get_or_load(self, url: str, snapshot: RepoSnapshot) -> str:
        """Devuelve el texto de `url` para `snapshot`, leyéndolo la primera vez."""
        key = (snapshot.slug, section_of(url))
        if key in self._texts:
            return self._texts[key]
        for document in snapshot.documents:
            if document.url == url:
                self._texts[key] = document.text
                return document.text
        raise KeyError(url)
