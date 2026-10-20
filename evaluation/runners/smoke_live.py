"""Live API acceptance checks against a dedicated local development deployment."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:18000"


def login(email):
    c = httpx.Client(base_url=BASE, timeout=25, trust_env=False)
    r = c.post("/api/auth/login", json={"email": email, "password": "CineweaveDemo!2026"})
    r.raise_for_status()
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    return c


def main():
    checks = []
    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})
        print(name, bool(condition), flush=True)
    c, other = login("demo@cineweave.local"), login("history@cineweave.local")
    session = c.post("/api/chat/sessions").json()
    sid, version = session["session_id"], 0
    check("anonymous_chat_rejected", httpx.post(BASE + "/api/chat/sessions", timeout=5).status_code in {401, 403})
    check("cross_user_session_hidden", other.get(f"/api/chat/sessions/{sid}").status_code == 404)
    def send(message, version, message_id=None, count=6):
        return c.post(f"/api/chat/sessions/{sid}/messages", json={"message": message,
            "client_message_id": message_id or str(uuid.uuid4()), "expected_state_version": version, "top_k": count})
    mid = str(uuid.uuid4())
    first = send("120分钟以内的科幻片，不要恐怖片", 0, mid)
    check("first_turn_ok", first.status_code == 200, first.status_code)
    first.raise_for_status()
    data = first.json()
    version = data["state_version"]
    check("real_semantic_ready", "semantic" in data["trace"] and not any(x.startswith("semantic:") for x in data["degraded_components"]))
    check("movie_ids_unique", len({m["movie_id"] for m in data["items"]}) == len(data["items"]))
    check("hard_filters_and_movie_scope", bool(data["items"]) and all(m["runtime_minutes"] and m["runtime_minutes"] <= 120
          and "Sci-Fi" in m["genres"] and "Horror" not in m["genres"] and m["title_type"] == "movie" for m in data["items"]))
    replay = send("120分钟以内的科幻片，不要恐怖片", 0, mid)
    check("message_replay_is_idempotent", replay.status_code == 200 and replay.json()["request_id"] == data["request_id"])
    check("reused_id_different_payload_rejected", send("100分钟以内", 0, mid).status_code == 409)
    check("stale_version_rejected", send("轻松一点", 0).status_code == 409)
    second = send("轻松一点", version).json()
    version = second["state_version"]
    check("unmentioned_constraints_retained", second["active_constraints"]["runtime_max"] == 120
          and second["active_constraints"]["exclude_genres"] == ["Horror"])
    third = send("时长不限了", version).json()
    version = third["state_version"]
    check("clear_runtime_only", third["active_constraints"]["runtime_max"] is None
          and third["active_constraints"]["exclude_genres"] == ["Horror"])
    if len(third["items"]) >= 3:
        removed = third["items"][2]["movie_id"]
        fourth = send("第三部看过了，换一部", version).json()
        version = fourth["state_version"]
        check("replace_previous_display_position", removed in fourth["active_constraints"]["excluded_movie_ids"]
              and removed not in [m["movie_id"] for m in fourth["items"]])
        event_id = str(uuid.uuid4())
        item = fourth["items"][0]
        payload = {"event_id": event_id, "request_id": fourth["request_id"], "movie_id": item["movie_id"], "feedback_type": "seen"}
        feedback = c.post(f"/api/chat/sessions/{sid}/feedback", json=payload)
        check("feedback_saved", feedback.status_code == 200)
        version = feedback.json()["state_version"]
        replay_feedback = c.post(f"/api/chat/sessions/{sid}/feedback", json=payload)
        check("feedback_deduped", replay_feedback.status_code == 200 and replay_feedback.json()["duplicate"])
        payload["movie_id"] = 999999
        check("feedback_must_belong_to_recommendation", c.post(f"/api/chat/sessions/{sid}/feedback", json=payload).status_code == 422)
    empty = send("2030年的电影", version).json()
    version = empty["state_version"]
    check("impossible_year_no_silent_relaxation", empty["status"] == "no_results" and not empty["items"]
          and empty["active_constraints"]["year_min"] == 2030)
    unclear = send("零血腥，保证适合所有儿童", version).json()
    version = unclear["state_version"]
    check("unsupported_guarantee_clarifies", unclear["status"] == "clarify")
    reset = send("清空本次条件", version).json()
    version = reset["state_version"]
    check("reset_clears_session_only", not reset["active_constraints"]["excluded_movie_ids"]
          and reset["active_constraints"]["year_min"] is None)
    restored = c.get(f"/api/chat/sessions/{sid}").json()
    check("session_persistence", restored["state_version"] == version and restored["total_turns"] >= 6)
    current_user = c.get('/api/users/me').json()
    wrong_user = other.get('/api/users/me').json()['user_id']
    check("classic_recommendation_ownership", c.post('/api/recommendations/recommend', json={'user_id': wrong_user}).status_code == 403)
    warm_sid = other.post('/api/chat/sessions').json()['session_id']
    warm = other.post(f'/api/chat/sessions/{warm_sid}/messages', json={'message':'科幻片，两小时以内',
        'client_message_id':str(uuid.uuid4()),'expected_state_version':0,'top_k':6})
    check("historical_user_chat", warm.status_code == 200)
    if warm.status_code == 200:
        trace = warm.json()['trace']
        check("historical_channels_and_deepfm", all(trace.get('channels',{}).get(x,0)>0 for x in ['semantic','youtubednn','item_based','genre_preference'])
              and any(m.get('preference_score') is not None for m in warm.json()['items']), trace)
    check("catalog_available", c.get('/api/movies',params={'page_size':5}).status_code == 200)
    check("search_available", c.get('/api/search/movies',params={'q':'Matrix'}).status_code == 200)
    if data['items']:
        movie_id=data['items'][0]['movie_id']
        check("movie_details_available", c.get(f'/api/movies/{movie_id}').status_code == 200)
        check("poster_through_frontend_proxy", httpx.get(f'http://127.0.0.1:13000/api/posters/{movie_id}.png',timeout=10).status_code == 200)
    # Two concurrent writes at the same version: one commit, one conflict.
    race = c.post('/api/chat/sessions').json()['session_id']
    def race_send(i):
        with httpx.Client(base_url=BASE,headers=dict(c.headers),timeout=25,trust_env=False) as worker:
            return worker.post(f'/api/chat/sessions/{race}/messages',json={'message':f'{100+i}分钟以内的喜剧',
                'client_message_id':str(uuid.uuid4()),'expected_state_version':0,'top_k':2}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=sorted(pool.map(race_send,[0,1]))
    check("concurrent_state_compare_and_swap", statuses == [200,409], statuses)
    output=ROOT/'evaluation/reports/generated/live_smoke.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    report={'checks':checks,'passed':sum(x['passed'] for x in checks),'total':len(checks),'mode':'live_local_rules_and_real_embeddings'}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
    c.close();other.close()
    raise SystemExit(report['passed']!=report['total'])


if __name__ == '__main__':
    main()
