import zlib

from pydantic import BaseModel

from btm.system.corpus import RepoSnapshot
from btm.system.taxonomy import Taxonomy


class SearchHit(BaseModel):
    url: str
    title: str
    score: float


RESULTS_PER_QUERY = 3

_SEPARATORS = str.maketrans({c: " " for c in ".,;:!?()[]{}\"'`/\\-_"})


def tokens(text: str) -> set[str]:
    return {t for t in text.lower().translate(_SEPARATORS).split() if t}


class ToolBox:
    def __init__(self, snapshot: RepoSnapshot, taxonomy: Taxonomy, *, run_id: str = "") -> None:
        self.snapshot = snapshot
        self.taxonomy = taxonomy
        self.run_id = run_id

    def search(self, query: str) -> list[SearchHit]:
        wanted = tokens(query)
        scored: list[tuple[float, int, SearchHit]] = []
        # El índice se recorre en el orden en que respondió el shard, que
        # depende de la petición.
        shard_order = sorted(
            range(len(self.snapshot.documents)),
            key=lambda i: zlib.crc32(f"{self.run_id}:{i}".encode()) % 997,
        )
        for position, index in enumerate(shard_order):
            document = self.snapshot.documents[index]
            overlap = len(wanted & tokens(f"{document.title} {document.text}"))
            score = overlap / max(len(wanted), 1)
            scored.append(
                (score, position, SearchHit(url=document.url, title=document.title, score=score))
            )
        scored.sort(key=lambda item: (-item[0], item[1]))
        # Se devuelve la primera página de resultados, y sólo lo que casa algo.
        return [hit for score, _, hit in scored if score > 0][:RESULTS_PER_QUERY]

    def fetch_page(self, url: str) -> str:
        for document in self.snapshot.documents:
            if document.url == url:
                return document.text
        raise KeyError(url)

    def lookup_taxonomy(self, code: str) -> dict:
        node = self.taxonomy.get(code)
        return {"code": node.code, "name": node.name, "description": node.description}
