"""Recálculo independiente de toda la estadística publicada.

Se ejecuta sobre los JSON crudos y no depende de ninguna acta: si un número del
artículo no sale de aquí, no se publica.
"""
import json
from math import comb, sqrt
from collections import Counter
from pathlib import Path

def fisher_one_sided(a, b, c, d):
    """P(X >= a) con marginales fijos. a=exitos grupo1, b=fallos g1, c=exitos g2, d=fallos g2."""
    n = a+b+c+d; tot = 0.0
    for x in range(0, min(a+b, a+c)+1):
        y = a+c-x
        if y < 0 or y > c+d: continue
        p = comb(a+b, x)*comb(c+d, y)/comb(n, a+c)
        if x >= a: tot += p
    return tot

def wilson(k, n):
    if n == 0: return (0,0)
    p = k/n; z = 1.96
    den = 1 + z*z/n
    c = (p + z*z/(2*n))/den
    h = z*sqrt(p*(1-p)/n + z*z/(4*n*n))/den
    return (max(0, c-h), min(1, c+h))

def compare(name, g1, g2, l1, l2, fields):
    print(f"\n=== {name}: {l1} (n={len(g1)}) vs {l2} (n={len(g2)}) ===")
    print(f"{'campo':46} {l1:>10} {l2:>10} {'p':>8}  IC95 del primero")
    for f in fields:
        if f not in g1[0]: continue
        a = sum(1 for r in g1 if r[f]); b = sum(1 for r in g2 if r[f])
        hi, lo = (a, b) if a >= b else (b, a)
        nh, nl = (len(g1), len(g2)) if a >= b else (len(g2), len(g1))
        p = fisher_one_sided(hi, nh-hi, lo, nl-lo)
        c = wilson(a, len(g1))
        print(f"{f:46} {a:>7}/{len(g1):<2} {b:>7}/{len(g2):<2} {p:>8.4f}  [{c[0]:.2f}, {c[1]:.2f}]")

# --- Run de confirmacion (escenario A1: orden de recuperacion) ---
conf = json.loads(Path('results/confirmacion.json').read_text(encoding='utf-8'))
C = [r for r in conf if r['cond'] == 'C']; D = [r for r in conf if r['cond'] == 'D']
compare("CONFIRMACION", C, D, "sin cod", "con cod",
    ['blames_sampling_as_primary','found_the_tiebreak','proposed_voting_or_retries',
     'proposed_temperature_to_fix_variance','identified_input_variation',
     'asked_for_instrumentation','built_own_measurement'])

# remedio-parche combinado
for nm, g in (("C", C), ("D", D)):
    k = sum(1 for r in g if r['proposed_voting_or_retries'] or r['proposed_temperature_to_fix_variance'])
    print(f"  parchea el sintoma {nm}: {k}/{len(g)}  IC95 {tuple(round(x,2) for x in wilson(k,len(g)))}")
a = sum(1 for r in C if r['proposed_voting_or_retries'] or r['proposed_temperature_to_fix_variance'])
b = sum(1 for r in D if r['proposed_voting_or_retries'] or r['proposed_temperature_to_fix_variance'])
print(f"  p = {fisher_one_sided(a,20-a,b,20-b):.5f}")

# --- A5 ---
a5 = json.loads(Path('results/a5-run.json').read_text(encoding='utf-8'))
J = [r for r in a5 if r['cond'] == 'j']; K = [r for r in a5 if r['cond'] == 'k']
compare("A5", J, K, "sin cod", "con cod",
    ['blamed_sampling_for_systematic','found_the_cache','correctly_attributed_the_tail',
     'separated_two_populations','proposed_temperature_to_fix_variance',
     'proposed_voting_or_retries','asked_for_instrumentation','built_own_measurement'])

# --- tier dentro de la condicion sin codigo ---
print("\n=== TIER, dentro de 'sin codigo' ===")
for nm, g, f in (("confirmacion", C, 'blames_sampling_as_primary'),
                 ("confirmacion", C, 'proposed_temperature_to_fix_variance'),
                 ("A5", J, 'blamed_sampling_for_systematic'),
                 ("A5", J, 'found_the_cache')):
    alto = [r for r in g if r['tier']=='alto']; medio = [r for r in g if r['tier']=='medio']
    a = sum(1 for r in medio if r[f]); b = sum(1 for r in alto if r[f])
    hi, lo = (a,b) if a>=b else (b,a)
    print(f"  {nm:13} {f:42} medio {a}/{len(medio)}  alto {b}/{len(alto)}  p={fisher_one_sided(hi,len(medio)-hi,lo,len(alto)-lo):.4f}")

# --- acumulado de instrumentacion ---
tot = sum(1 for r in conf+a5 if r['asked_for_instrumentation'])
print(f"\n=== ACUMULADO ===\n  pide instrumentacion antes de concluir: {tot}/{len(conf)+len(a5)}")
built = sum(1 for r in a5 if r['built_own_measurement'])
print(f"  fabrica su propia medicion (solo A5, es donde se codifico): {built}/{len(a5)}")
