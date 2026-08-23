"""Contabilidad de las búsquedas que consume una clasificación."""


class SearchBudgetExhausted(Exception):
    """Se lanza al pedir una búsqueda cuando ya no quedan."""


class Budget:
    """Contabiliza las búsquedas de una clasificación."""

    def __init__(self, max_searches: int) -> None:
        self.max_searches = max_searches
        self.spent = 0

    @property
    def remaining(self) -> int:
        return max(self.max_searches - self.spent, 0)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    def spend(self) -> None:
        if self.exhausted:
            raise SearchBudgetExhausted()
        self.spent += 1

    def declared_ceiling(self, answered: int, planned: int) -> float:
        """Techo de confianza según la fracción de consultas que dieron respuesta."""
        return min(1.0, answered / max(planned, 1))
