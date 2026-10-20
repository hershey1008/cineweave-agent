"""Exercise a running local app; reports rule-mode functional results separately."""
import argparse
import json
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def run(base):
    cases = json.loads((ROOT / "evaluation/datasets/conversation_cases.json").read_text(encoding="utf-8"))
    results = []
    with httpx.Client(base_url=base, timeout=25, trust_env=False) as client:
        response = client.post("/api/auth/login", json={"email": "demo@cineweave.local", "password": "CineweaveDemo!2026"})
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        for case in cases:
            session = client.post("/api/chat/sessions").json()
            version = 0
            turns = []
            for turn in case["turns"]:
                started = time.perf_counter()
                response = client.post(f"/api/chat/sessions/{session['session_id']}/messages", json={
                    "message": turn["message"], "client_message_id": str(uuid.uuid4()),
                    "expected_state_version": version, "top_k": 3})
                data = response.json()
                state = data.get("active_constraints", {})
                valid_state = response.status_code == 200 and all(state.get(k) == v for k, v in turn["expect"].items())
                items = data.get("items", [])
                valid_items = all((not state.get("runtime_max") or (m.get("runtime_minutes") and m["runtime_minutes"] <= state["runtime_max"]))
                    and not set(m["genres"]) & set(state.get("exclude_genres", []))
                    and set(state.get("include_genres", [])) <= set(m["genres"])
                    and m.get("title_type") == "movie" for m in items)
                turns.append({"state_ok": valid_state, "constraints_ok": valid_items,
                    "item_count": len(items), "status": data.get("status"), "parser_mode": data.get("parser_mode"),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
                version = data.get("state_version", version)
            results.append({"case_id": case["case_id"], "passed": all(t["state_ok"] and t["constraints_ok"] for t in turns), "turns": turns})
            print(case["case_id"], results[-1]["passed"], flush=True)
    report = {"protocol": "rules_functional_fixtures_v1", "not_a_human_relevance_benchmark": True,
              "cases": len(results), "passed": sum(r["passed"] for r in results),
              "turns": sum(len(r["turns"]) for r in results), "results": results}
    output = ROOT / "evaluation/reports/generated/conversations.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    report = run(args.base_url)
    raise SystemExit(report["passed"] != report["cases"])
