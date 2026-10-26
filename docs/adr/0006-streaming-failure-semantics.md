# ADR 0006: Streaming failure semantics: no silent mid-stream failover

## Status
Accepted (initial release).

## Context
With server-sent-event streaming, output already sent to the client cannot be retracted. Silently switching providers mid-stream would duplicate or corrupt output (spec §9.4).

## Decision
Fallback and retry are permitted only before the first content event has been emitted. Once streaming has started, a provider failure terminates the stream with a single, well-defined terminal error event in the documented format; the logical request and attempts record the failure and any partial usage. Clients can therefore distinguish a complete stream, a clean error response, and a terminated stream.

## Consequences
Client-visible behaviour is deterministic and testable, including disconnect tests (spec §17.5). Cost: a mid-stream failure cannot be transparently recovered; the client must decide whether to issue a new logical request.
