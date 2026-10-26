# Public Inference API

Base URL (local): `http://localhost:8000`. All inference endpoints require a
gateway API key: `Authorization: Bearer <key>`. Keys are shown once at
creation, stored only as hashes, and can expire or be revoked (spec §6.3).

## Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/v1/models` | List model aliases the caller's project may access, in OpenAI list format | API key |
| POST | `/v1/chat/completions` | Chat completion for a model alias; streaming via `"stream": true` | API key |
| GET | `/health/live` | Process liveness only — no dependency checks | none |
| GET | `/health/ready` | Readiness: PostgreSQL (and Redis, when required by config) reachable; optional providers do **not** fail readiness unless the deployment requires them | none |
| GET | `/metrics` | Prometheus metrics (spec §14.1) | network-restricted locally |

Every response carries the logical request ID (`X-Request-Id` header and in
trace/log records). The request ID is constant across provider attempts;
attempt IDs appear in admin request detail, not in the public response.

## Chat completions

- Messages: `system`, `user`, `assistant` roles.
- `model` is a ModelRail **alias**, resolved to provider routes by policy.
- Generation parameters are passed only when the selected adapter supports
  them; support is declared per route capability.
- Usage is returned when available, with its basis documented in the admin
  views: provider-reported, calculated, estimated, simulated, or unknown
  (unknown usage is never fabricated — spec §10).

### Unknown and unsupported fields (spec §6.1)

Unknown fields are **not** silently ignored:

| Case | Behaviour |
|---|---|
| Unknown or unsupported top-level field | `422` in the standard error envelope with code `unsupported_field`, naming the field |
| Other malformed values (wrong type, out of range) | `422` in the standard error envelope with code `validation_error` |
| Field that would materially change model behaviour | Never dropped silently — either honoured or rejected as above |

## Error format

Errors are stable and documented; the shape mirrors the OpenAI error object
with a ModelRail error code:

```json
{
  "error": {
    "message": "Project budget would be exceeded by this request.",
    "type": "rate_limit_error",
    "code": "budget_exceeded",
    "request_id": "req_..."
  }
}
```

Common codes: `invalid_api_key`, `api_key_expired`, `api_key_revoked`,
`model_not_found`, `model_not_allowed`, `unknown_field`,
`unsupported_parameter`, `request_too_large`, `rate_limit_exceeded`,
`budget_exceeded`, `no_eligible_route`, `provider_timeout`,
`provider_unavailable`, `deadline_exceeded`. Rate-limit and budget errors
include retry metadata (`Retry-After` where applicable, spec §11).

## Streaming semantics

- `"stream": true` returns Server-Sent Events in the OpenAI chunk format,
  in order, terminated by `[DONE]` on success.
- Retries/fallback happen only **before** the first content chunk is sent
  (ADR-0006). After content has started, a provider failure ends the stream
  with one terminal error event; the client never receives silently
  duplicated output from a second provider.
- A client disconnect ends the logical request; the attempt record and any
  partial/provider-reported usage are persisted as-is.
