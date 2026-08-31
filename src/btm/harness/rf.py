"""Etiquetas y entrenamiento de la cabeza de bosque aleatorio.

Esto es arnés: nunca se entrega. Son dos pasos.

`labels` clasifica cada repositorio del corpus con el sistema sano y el modelo
real, dándole el contexto completo del repositorio en vez de los cuatro
documentos que caben en la ventana. De ahí sale un par (texto, código) por
repositorio, que se guarda con el modelo que lo produjo y la fecha.

`train` ajusta con esos pares un TF-IDF y un bosque pequeño, y lo congela en
disco. El bosque no tiene que acertar mucho: tiene que ser determinista y
depender de los documentos que se le pasan, que es lo que hace comparable el
brazo sin modelo de lenguaje con el brazo con él.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import KFold, cross_val_score

from btm.harness.model import AzureModel
from btm.system.classifier import build_prompt
from btm.system.corpus import RepoSnapshot, load_all
from btm.system.taxonomy import Taxonomy
from btm.variants.RF.model import HEAD_PATH, save_head

# El texto de un repositorio es el de todos sus documentos, unidos como los une
# la cabeza al leerlos del prompt.
DOCUMENT_JOIN = "\n"

FOLDS = 5
# Cien árboles dejan la probabilidad en pasos de 0,01, los mismos dos
# decimales con los que se guarda la confianza.
FOREST = {"n_estimators": 100, "random_state": 0, "n_jobs": 1}
VECTORIZER = {
    "strip_accents": "unicode",
    "sublinear_tf": True,
    "max_features": 4000,
    "stop_words": "english",
}


def full_text(snapshot: RepoSnapshot) -> str:
    return DOCUMENT_JOIN.join(document.text for document in snapshot.documents)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def label_one(snapshot: RepoSnapshot, taxonomy: Taxonomy, deployment: str) -> dict:
    """Pide el juicio del sistema sano sobre el repositorio entero."""
    documents = [document.text for document in snapshot.documents]
    prompt = build_prompt(snapshot, taxonomy, documents)
    raw = AzureModel(deployment=deployment).complete([{"role": "user", "content": prompt}])
    payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    text = full_text(snapshot)
    return {
        "slug": snapshot.slug,
        "documents": len(snapshot.documents),
        "characters": len(text),
        "text_sha256": sha256(text),
        "code": payload["code"],
        "confidence": float(payload["confidence"]),
        "justification": payload["justification"],
    }


def _labels(args: argparse.Namespace) -> None:
    taxonomy = Taxonomy.load(args.taxonomy)
    snapshots = load_all(args.corpus)
    print(f"{len(snapshots)} proyectos | modelo: {args.deployment}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda s: label_one(s, taxonomy, args.deployment), snapshots))

    known = {leaf.code for leaf in taxonomy.leaves()}
    unknown = [row["slug"] for row in rows if row["code"] not in known]
    if unknown:
        raise SystemExit(f"códigos fuera de la taxonomía: {unknown}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "model": args.deployment,
                "generated_at": dt.date.today().isoformat(),
                "corpus": str(args.corpus),
                "context": "todos los documentos del repositorio, sin truncar",
                "labels": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["code"]] = counts.get(row["code"], 0) + 1
    for code, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {code}")
    print(f"{len(rows)} etiquetas -> {args.out}")


def _train(args: argparse.Namespace) -> None:
    blob = json.loads(args.labels.read_text(encoding="utf-8"))
    by_slug = {snapshot.slug: snapshot for snapshot in load_all(args.corpus)}

    texts: list[str] = []
    codes: list[str] = []
    for row in blob["labels"]:
        text = full_text(by_slug[row["slug"]])
        if sha256(text) != row["text_sha256"]:
            raise SystemExit(f"el texto de {row['slug']} no es el que se etiquetó")
        texts.append(text)
        codes.append(row["code"])

    vectorizer = TfidfVectorizer(**VECTORIZER)
    matrix = vectorizer.fit_transform(texts)
    forest = RandomForestClassifier(**FOREST)
    forest.fit(matrix, codes)

    fitted = forest.score(matrix, codes)
    # Particiones sin estratificar: hay clases con un solo miembro, y ninguna
    # partición estratificada las reparte.
    folds = KFold(n_splits=FOLDS, shuffle=True, random_state=0)
    held_out = cross_val_score(RandomForestClassifier(**FOREST), matrix, codes, cv=folds).mean()

    path = save_head(
        vectorizer,
        forest,
        args.out,
        metadata={
            "model": blob["model"],
            "labels_generated_at": blob["generated_at"],
            "trained_at": dt.date.today().isoformat(),
            "corpus": str(args.corpus),
            "labels": len(codes),
            "classes": sorted(set(codes)),
            "vectorizer": VECTORIZER,
            "forest": FOREST,
        },
    )
    print(f"{len(codes)} pares | {len(vectorizer.vocabulary_)} términos | {len(set(codes))} clases")
    print(f"acierto sobre lo ajustado: {fitted:.2f} | fuera de muestra ({FOLDS} particiones): {held_out:.2f}")
    print(f"cabeza -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="btm-rf")
    parser.add_argument("--corpus", type=Path, default=Path("data/scenario"))
    parser.add_argument("--taxonomy", type=Path, default=Path("data/taxonomy.yaml"))
    sub = parser.add_subparsers(dest="stage", required=True)

    labels = sub.add_parser("labels")
    labels.add_argument("--out", type=Path, default=Path("data/rf/labels.json"))
    labels.add_argument("--deployment", default=os.environ.get("BTM_DEPLOYMENT", "gpt-5-mini"))
    labels.add_argument("--workers", type=int, default=6)
    labels.set_defaults(fn=_labels)

    train = sub.add_parser("train")
    train.add_argument("--labels", type=Path, default=Path("data/rf/labels.json"))
    train.add_argument("--out", type=Path, default=HEAD_PATH)
    train.set_defaults(fn=_train)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
