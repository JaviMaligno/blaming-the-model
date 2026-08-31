import json

from btm.system.trace import Trace


def test_events_are_numbered_in_order() -> None:
    trace = Trace()
    trace.record("input", slug="acme")
    trace.record("tool_call", name="search", query="pagos")
    assert [e.seq for e in trace.events] == [0, 1]
    assert trace.events[1].payload["name"] == "search"


def test_jsonl_has_one_line_per_event() -> None:
    trace = Trace()
    trace.record("input", slug="acme")
    trace.record("final", code="business.payments")
    lines = trace.to_jsonl().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["payload"]["code"] == "business.payments"
