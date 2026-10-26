"""Integration tests against the full FastAPI app (SQLite test database)."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db.models import UsageEvent
from app.main import app
from tests.conftest import ADMIN, add_route, make_project

CHAT = "/v1/chat/completions"


def _chat(client, auth, content="echo: hello", model="alias-main", **extra):
    body = {"model": model, "messages": [{"role": "user", "content": content}]}
    body.update(extra)
    return client.post(CHAT, headers=auth, json=body)


def test_health(client):
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").status_code == 200


def test_models_requires_auth_and_lists_aliases(client, db, project):
    add_route(db, "alias-main")
    assert client.get("/v1/models").status_code == 401
    resp = client.get("/v1/models", headers=project["auth"])
    assert resp.status_code == 200
    assert any(m["id"] == "alias-main" for m in resp.json()["data"])


def test_chat_completion_success_shape(client, db, project):
    add_route(db, "alias-main")
    resp = _chat(client, project["auth"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "hello"
    assert (
        body["usage"]["total_tokens"] == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    )
    mr = body["modelrail"]
    assert mr["provider"] == "mock" and mr["attempts"] == 1 and mr["cost_basis"] == "simulated"
    assert resp.headers["x-request-id"] == mr["request_id"]


def test_chat_records_request_attempt_usage_and_settles_budget(client, db):
    project = make_project(db, budget="10.00")
    add_route(db, "alias-main")
    resp = _chat(client, project["auth"])
    assert resp.status_code == 200
    request_id = resp.json()["modelrail"]["request_id"]
    detail = client.get(f"/admin/v1/requests/{request_id}", headers=ADMIN)
    assert detail.status_code == 200
    detail = detail.json()
    assert detail["status"] == "succeeded" and len(detail["attempts"]) == 1
    assert detail["attempts"][0]["status"] == "succeeded"
    usage = client.get("/admin/v1/usage", headers=ADMIN, params={"project_id": project["project_id"]}).json()
    budget = next(b for b in usage["budgets"] if b["project_id"] == project["project_id"])
    assert float(budget["settled"]) > 0 and budget["reconciliation_needed"] == 0
    events = db.execute(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.request_id == request_id)
    ).scalar_one()
    assert events == 1


def test_streaming_sse_order_and_done(client, db, project):
    add_route(db, "alias-main")
    with client.stream(
        "POST",
        CHAT,
        headers=project["auth"],
        json={
            "model": "alias-main",
            "stream": True,
            "messages": [{"role": "user", "content": "echo: one two three"}],
        },
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert text.rstrip().endswith("data: [DONE]")
    chunks = [line[6:] for line in text.splitlines() if line.startswith("data: ") and "[DONE]" not in line]
    contents = "".join(json.loads(c)["choices"][0]["delta"].get("content", "") for c in chunks)
    assert contents == "one two three"
    finishes = [json.loads(c)["choices"][0]["finish_reason"] for c in chunks]
    assert finishes[-1] == "stop"


def test_idempotency_replay_does_not_double_count(client, db, project):
    add_route(db, "alias-main")
    headers = {**project["auth"], "Idempotency-Key": "order-123"}
    first = client.post(
        CHAT,
        headers=headers,
        json={"model": "alias-main", "messages": [{"role": "user", "content": "echo: once"}]},
    )
    second = client.post(
        CHAT,
        headers=headers,
        json={"model": "alias-main", "messages": [{"role": "user", "content": "echo: once"}]},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["modelrail"]["request_id"] == second.json()["modelrail"]["request_id"]
    count = db.execute(select(func.count()).select_from(UsageEvent)).scalar_one()
    assert count == 1


def test_admin_crud_flow(client, db):
    created = client.post("/admin/v1/projects", headers=ADMIN, json={"name": "crud-proj"})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    key = client.post("/admin/v1/keys", headers=ADMIN, json={"project_id": project_id, "name": "k1"})
    assert key.status_code == 201
    assert key.json()["api_key"].startswith("mr_live_")  # shown once
    listing = client.get("/admin/v1/keys", headers=ADMIN, params={"project_id": project_id})
    assert "api_key" not in listing.json()["data"][0]  # never returned again
    route = client.post(
        "/admin/v1/models",
        headers=ADMIN,
        json={"alias": "crud-alias", "provider": "mock", "upstream_model": "mock-1", "priority": 5},
    )
    assert route.status_code == 201
    updated = client.put(f"/admin/v1/models/{route.json()['id']}", headers=ADMIN, json={"priority": 1})
    assert updated.json()["priority"] == 1 and updated.json()["configuration_version"] == 2
    audit = client.get("/admin/v1/audit-events", headers=ADMIN)
    actions = {e["action"] for e in audit.json()["data"]}
    assert {"project.create", "api_key.create", "model_route.create"} <= actions


def test_admin_evaluation_good_vs_degraded_gate(client):
    good = client.post(
        "/admin/v1/evaluations",
        headers=ADMIN,
        json={"candidate_model": "mock-good", "baseline_model": "mock-good"},
    )
    assert good.status_code == 201, good.text
    assert good.json()["status"] == "completed"
    assert good.json()["summary"]["gate"]["passed"] is True
    degraded = client.post(
        "/admin/v1/evaluations",
        headers=ADMIN,
        json={"candidate_model": "mock-degraded", "baseline_model": "mock-good"},
    )
    assert degraded.json()["summary"]["gate"]["passed"] is False
    assert degraded.json()["summary"]["gate"]["failures"]
    fetched = client.get(f"/admin/v1/evaluations/{degraded.json()['id']}", headers=ADMIN)
    assert fetched.status_code == 200


def test_metrics_endpoint(client, db, project):
    add_route(db, "alias-main")
    _chat(client, project["auth"])
    text = client.get("/metrics").text
    assert "modelrail_logical_requests_total" in text
    assert "modelrail_provider_attempts_total" in text


def test_openai_sdk_can_talk_to_modelrail(db, project):
    """The official OpenAI SDK against a real uvicorn server (spec section 18)."""
    import threading
    import time

    import httpx
    import uvicorn
    from openai import OpenAI

    add_route(db, "alias-main")
    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        probe = httpx.Client(trust_env=False)  # ignore proxy env on this VM
        for _ in range(50):
            try:
                if probe.get("http://127.0.0.1:8765/health/live", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        sdk = OpenAI(
            api_key=_raw_key(db, project),
            base_url="http://127.0.0.1:8765/v1",
            http_client=httpx.Client(trust_env=False),
        )
        completion = sdk.chat.completions.create(
            model="alias-main", messages=[{"role": "user", "content": "echo: via sdk"}]
        )
        assert completion.choices[0].message.content == "via sdk"
        assert completion.usage.total_tokens > 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _raw_key(db, project):
    from app.core.security import generate_api_key
    from app.db.models import ApiKey

    plaintext, prefix, key_hash = generate_api_key()
    db.add(ApiKey(project_id=project["project_id"], name="sdk", key_prefix=prefix, key_hash=key_hash))
    db.commit()
    return plaintext
