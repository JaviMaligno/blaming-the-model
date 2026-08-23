from pydantic import BaseModel

from btm.system.corpus import RepoSnapshot
from btm.system.taxonomy import Taxonomy


class SearchHit(BaseModel):
    url: str
    title: str
    score: float


def tokens(text: str) -> set[str]:
    return {t for t in text.lower().split() if t}


class ToolBox:
    def __init__(self, snapshot: RepoSnapshot, taxonomy: Taxonomy, *, run_id: str = "") -> None:
        self.snapshot = snapshot
        self.taxonomy = taxonomy
        self.run_id = run_id

    def search(self, query: str) -> list[SearchHit]:
        wanted = tokens(query)
        scored: list[tuple[float, int, SearchHit]] = []
        for position, document in enumerate(self.snapshot.documents):
            overlap = len(wanted & tokens(document.text))
            score = overlap / max(len(wanted), 1)
            scored.append(
                (score, position, SearchHit(url=document.url, title=document.title, score=score))
            )
        # Empates estables: gana el que llegó antes al índice.
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [hit for _, _, hit in scored]

    def fetch_page(self, url: str) -> str:
        for document in self.snapshot.documents:
            if document.url == url:
                return document.text
        raise KeyError(url)

    def lookup_taxonomy(self, code: str) -> dict:
        node = self.taxonomy.get(code)
        return {"code": node.code, "name": node.name, "description": node.description}
