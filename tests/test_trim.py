"""El recortador de trazas del arnés.

Esto es arnés: recorta lo que se entrega, y por eso vive fuera del sistema.
"""

import json

from btm.harness.trim import poor, shallow
from btm.system.trace import Trace


def full_trace() -> Trace:
    trace = Trace()
    trace.record("input", slug="acme--pay")
    trace.record("tool_call", name="search", query="pay")
    trace.record("context_documents", urls=["https://github.com/acme/pay#0"])
    trace.record("budget", remaining=1)
    trace.record("final", code="business.payments")
    return trace


def test_the_trimmed_trace_keeps_only_the_input_and_the_outcome() -> None:
    assert [e.kind for e in poor(full_trace()).events] == ["input", "final"]


def test_trimming_does_not_mutate_the_original() -> None:
    trace = full_trace()
    poor(trace)
    assert len(trace.events) == 5


def test_the_payloads_survive_the_trim() -> None:
    kept = poor(full_trace()).events
    assert kept[0].payload["slug"] == "acme--pay"
    assert kept[1].payload["code"] == "business.payments"


def test_trimming_the_dumped_log_renumbers_from_zero() -> None:
    events = [json.loads(line) for line in shallow(full_trace().to_jsonl()).splitlines()]
    assert [e["kind"] for e in events] == ["input", "final"]
    # Sin huecos en `seq`: el registro no dice cuántos eventos no están.
    assert [e["seq"] for e in events] == [0, 1]


def test_a_log_that_was_already_trimmed_comes_out_the_same() -> None:
    once = shallow(full_trace().to_jsonl())
    assert shallow(once) == once
