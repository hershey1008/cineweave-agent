"""Score supplied, reviewed qrels against saved retrieval runs; never invent labels."""
import argparse
import csv
import json
import math
from pathlib import Path


def score(qrels_path, runs_path):
    labels = {}
    with qrels_path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            grade = int(row["grade"])
            if grade not in {0, 1, 2} or not row["annotator"].strip():
                raise ValueError("Each label requires grade 0/1/2 and an annotator")
            labels.setdefault(row["query_id"], {})[int(row["movie_id"])] = grade
    if not labels:
        raise ValueError("No human relevance labels were supplied; nDCG/Success cannot be reported")
    runs = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    output = []
    for run in runs:
        qid = run["query_id"]
        if qid not in labels:
            continue
        ids = [int(mid) for mid in run["movie_ids"][:10]]
        grades = [labels[qid].get(mid, 0) for mid in ids]
        ideal = sorted(labels[qid].values(), reverse=True)[:10]
        dcg = lambda values: sum((2 ** value - 1) / math.log2(i + 2) for i, value in enumerate(values))
        output.append({"query_id": qid, "ndcg10": dcg(grades) / dcg(ideal) if dcg(ideal) else None,
                       "success10": int(2 in grades),
                       "judged_fraction": sum(mid in labels[qid] for mid in ids) / max(1, len(ids))})
    if not output:
        raise ValueError("No matching labelled queries in retrieval run")
    return {"queries": output, "note": "Unjudged pooled items use grade 0; inspect judged_fraction and pool completeness."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(args.qrels, args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
