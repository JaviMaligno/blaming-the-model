"""Two-level taxonomy of application domains, loaded from YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class TaxonomyNode(BaseModel):
    """A single division or subdivision of the taxonomy."""

    code: str
    name: str
    description: str
    parent: str | None = None


class Taxonomy(BaseModel):
    """All taxonomy nodes, flattened and indexed by code."""

    nodes: dict[str, TaxonomyNode]

    @classmethod
    def load(cls, path: Path) -> "Taxonomy":
        """Read the YAML file and flatten divisions and their children."""
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        nodes: dict[str, TaxonomyNode] = {}
        for code, division in raw.items():
            nodes[code] = TaxonomyNode(
                code=code, name=division["name"], description=division["description"]
            )
            for child_code, child in division.get("children", {}).items():
                nodes[child_code] = TaxonomyNode(
                    code=child_code,
                    name=child["name"],
                    description=child["description"],
                    parent=code,
                )
        return cls(nodes=nodes)

    def get(self, code: str) -> TaxonomyNode:
        """Return the node with this code, raising KeyError if it is unknown."""
        return self.nodes[code]

    def leaves(self) -> list[TaxonomyNode]:
        """Return every node that hangs from a division."""
        return [node for node in self.nodes.values() if node.parent is not None]
