import pytest

from btm.system.budget import Budget, SearchBudgetExhausted


def test_each_search_costs_one() -> None:
    budget = Budget(max_searches=3)
    budget.spend()
    assert budget.remaining == 2


def test_the_fourth_search_of_a_budget_of_three_is_denied() -> None:
    budget = Budget(max_searches=3)
    for _ in range(3):
        budget.spend()
    assert budget.exhausted
    with pytest.raises(SearchBudgetExhausted):
        budget.spend()


def test_a_full_plan_earns_a_ceiling_of_one() -> None:
    assert Budget(max_searches=4).declared_ceiling(answered=3, planned=3) == pytest.approx(1.0)


def test_a_partial_plan_lowers_the_ceiling() -> None:
    assert Budget(max_searches=4).declared_ceiling(answered=2, planned=3) == pytest.approx(2 / 3)


def test_the_ceiling_never_exceeds_one() -> None:
    assert Budget(max_searches=9).declared_ceiling(answered=5, planned=3) == pytest.approx(1.0)
