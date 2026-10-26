# Shared schemas

Cross-component schema definitions live with their owners in this release:

- Public inference API schemas: `apps/gateway/app/schemas/chat.py`
- Administrative API schemas: `apps/gateway/app/schemas/admin.py`
- Evaluation dataset schema: `packages/evals/modelrail_evals/dataset.py`
  (validated by `validate_cases` on load)

This package is reserved for schemas that gain a second consumer (e.g. a
TypeScript client generated from the gateway's OpenAPI document, available at
`/openapi.json` on a running gateway).
