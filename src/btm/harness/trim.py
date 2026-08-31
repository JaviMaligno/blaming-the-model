"""Recorte de las trazas antes de entregarlas.

Esto es arnés: nunca se entrega. Al investigador se le da la entrada de cada
corrida y su resultado, y nada más. Los eventos intermedios existen y el
sistema los escribe, pero enseñarlos aquí sería contestar la pregunta: lo que
hay que reconstruir razonando es justo lo que pasó entre uno y otro.

Los eventos que sobreviven se renumeran desde cero, para que el registro no
lleve huecos en `seq` delatando cuántos no están.
"""

import json

from btm.system.trace import Trace

# Los kinds que sobreviven al recorte: la entrada de la corrida y su resultado.
POOR_KINDS = ("input", "final")


def poor(trace: Trace) -> Trace:
    """Devuelve una traza nueva con sólo la entrada y el resultado."""
    kept = Trace()
    for event in trace.events:
        if event.kind in POOR_KINDS:
            kept.record(event.kind, **event.payload)
    return kept


def shallow(trace_jsonl: str) -> str:
    """Lo mismo, sobre una traza ya volcada a JSON Lines."""
    kept = Trace()
    for line in trace_jsonl.strip().splitlines():
        event = json.loads(line)
        if event["kind"] in POOR_KINDS:
            kept.record(event["kind"], **event["payload"])
    return kept.to_jsonl()
