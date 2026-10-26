# Administrative API

Base path: `/admin/v1`. Administrative access is **independently
authenticated** (admin identity/token from configuration) and never relies on
an inference API key (spec §6.3). Roles: platform admin, project admin,
read-only operator. Every mutating admin operation writes an audit event
(spec §12.10) without secrets or unredacted payloads.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/admin/v1/models` | List model routes/aliases with provider, priority, capabilities, enabled state, config version |
| POST | `/admin/v1/models` | Create a model route |
| PUT | `/admin/v1/models/{id}` | Update a model route |
| GET | `/admin/v1/projects` | List projects (tenant-scoped for project admins) |
| POST | `/admin/v1/projects` | Create a project |
| GET | `/admin/v1/keys` | List API keys for a project — prefix, status, expiry, last used; **never the secret** |
| POST | `/admin/v1/keys` | Create an API key — the plaintext key is returned **once**, in this response only |
| DELETE | `/admin/v1/keys/{id}` | Revoke an API key (effective promptly) |
| GET | `/admin/v1/policies` | List project policies (allowlists, limits, budget, routing policy) |
| POST | `/admin/v1/policies` | Create a policy |
| PUT | `/admin/v1/policies/{id}` | Update a policy |
| GET | `/admin/v1/usage` | Usage and estimated cost, filterable by project, model, time range, usage source |
| GET | `/admin/v1/requests` | Search logical requests (status, model, provider, time filters) |
| GET | `/admin/v1/requests/{id}` | One logical request with its provider-attempt timeline, routing decision and usage |
| POST | `/admin/v1/evaluations` | Start an evaluation run (dataset version, baseline/candidate, configuration) |
| GET | `/admin/v1/evaluations/{id}` | Evaluation run status and report (metrics, latency, cost, regression verdict) |
| GET | `/admin/v1/audit-events` | Audit events, filterable by organisation, actor, action, resource |

## Conventions

- **Pagination:** cursor or `limit`/`offset` on all list endpoints, with
  `total` where cheap to compute; responses are JSON objects with a `data`
  array.
- **Tenant isolation:** every query is scoped by organisation/project at the
  service boundary. A project admin changing a resource ID to another
  project's resource gets `404`/`403`, never the resource (spec §16.2,
  security tests §17.4).
- **Validation & errors:** same error object shape as the public API
  (`error.message/type/code/request_id`), plus field-level detail for
  `422` validation failures.
- **Secrets:** key secrets, provider credentials and authorisation headers
  never appear in responses, audit metadata or logs (spec §16.1).
