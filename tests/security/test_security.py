"""Security tests (spec 17.4): auth, tenant isolation, payload limits, secrets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import generate_api_key, hash_admin_token
from app.db.models import AdminIdentity, ApiKey
from tests.conftest import ADMIN, add_route, make_project

CHAT = "/v1/chat/completions"
BODY = {"model": "alias-sec", "messages": [{"role": "user", "content": "echo: hi"}]}


def test_missing_and_invalid_keys_rejected(client, db, project):
    add_route(db, "alias-sec")
    assert client.post(CHAT, json=BODY).status_code == 401
    bad = client.post(CHAT, headers={"Authorization": "Bearer mr_live_nope"}, json=BODY)
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_api_key"


def test_revoked_key_rejected_promptly(client, db, project):
    add_route(db, "alias-sec")
    assert client.post(CHAT, headers=project["auth"], json=BODY).status_code == 200
    key_row = db.query(ApiKey).filter(ApiKey.project_id == project["project_id"]).first()
    revoked = client.delete(f"/admin/v1/keys/{key_row.id}", headers=ADMIN)
    assert revoked.status_code == 200
    assert client.post(CHAT, headers=project["auth"], json=BODY).status_code == 401


def test_expired_key_rejected(client, db):
    project = make_project(db)
    add_route(db, "alias-sec")
    plaintext, prefix, key_hash = generate_api_key()
    db.add(
        ApiKey(
            project_id=project["project_id"],
            name="old",
            key_prefix=prefix,
            key_hash=key_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db.commit()
    resp = client.post(CHAT, headers={"Authorization": f"Bearer {plaintext}"}, json=BODY)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "expired_api_key"


def test_admin_requires_separate_token(client, db, project):
    # A gateway API key is NOT an admin credential
    assert client.get("/admin/v1/projects", headers=project["auth"]).status_code == 401
    assert client.get("/admin/v1/projects").status_code == 401


def test_viewer_is_read_only(client, db):
    token = "viewer-token-123"
    db.add(
        AdminIdentity(name="v", role="viewer", token_prefix=token[:16], token_hash=hash_admin_token(token))
    )
    db.commit()
    headers = {"X-Admin-Token": token}
    assert client.get("/admin/v1/projects", headers=headers).status_code == 200
    assert client.post("/admin/v1/projects", headers=headers, json={"name": "nope"}).status_code == 403


def test_project_admin_cannot_cross_tenants(client, db):
    org_a = make_project(db, org_name="Tenant A")
    org_b = make_project(db, org_name="Tenant B")
    token = "pa-token-123"
    db.add(
        AdminIdentity(
            name="pa",
            role="project_admin",
            organization_id=org_a["org_id"],
            token_prefix=token[:16],
            token_hash=hash_admin_token(token),
        )
    )
    db.commit()
    headers = {"X-Admin-Token": token}
    # own tenant fine
    own = client.get("/admin/v1/projects", headers=headers)
    assert all(p["organization_id"] == org_a["org_id"] for p in own.json()["data"])
    # other tenant's usage is forbidden
    cross = client.get("/admin/v1/usage", headers=headers, params={"project_id": org_b["project_id"]})
    assert cross.status_code == 403
    cross_req = client.get("/admin/v1/requests", headers=headers, params={"project_id": org_b["project_id"]})
    assert cross_req.status_code == 403


def test_oversized_payload_rejected(client, db, project):
    add_route(db, "alias-sec")
    big = "x" * 300_000
    resp = client.post(
        CHAT,
        headers=project["auth"],
        content='{"model": "alias-sec", "messages": [{"role": "user", "content": "' + big + '"}]}',
    )
    # middleware content-length guard (413) fires before schema validation
    assert resp.status_code in (413, 422)


def test_unsupported_field_rejected_not_ignored(client, db, project):
    add_route(db, "alias-sec")
    resp = client.post(CHAT, headers=project["auth"], json={**BODY, "logit_bias": {"1": 5}})
    assert resp.status_code == 422  # extra=forbid: documented handling, never silent


def test_unknown_model_and_disallowed_model(client, db, project):
    resp = client.post(
        CHAT, headers=project["auth"], json={"model": "nope", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 404
    limited = make_project(db, allowed=["only-this"])
    resp2 = client.post(
        CHAT,
        headers=limited["auth"],
        json={"model": "alias-sec", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "model_not_allowed"


def test_secrets_not_in_responses_or_errors(client, db, project):
    add_route(db, "alias-sec")
    resp = client.post(CHAT, headers=project["auth"], json=BODY)
    assert "test-pepper" not in resp.text
    assert project["api_key"] not in resp.text
    keys = client.get("/admin/v1/keys", headers=ADMIN, params={"project_id": project["project_id"]})
    for entry in keys.json()["data"]:
        assert "key_hash" not in entry and "api_key" not in entry
