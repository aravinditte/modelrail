# ADR 0005: Provider usage accounting with explicit provenance

## Status
Accepted (initial release).

## Context
Providers report usage inconsistently; some failures occur after partial generation; Ollama/local inference has no invoice. Inventing numbers would make metering untrustworthy (spec §9.5, §10.1, §10.3).

## Decision
Every usage record carries a provenance: provider-reported (preferred), locally calculated, estimated, mock-simulated, or unknown. Costs are computed with Decimal arithmetic from a versioned price schedule and stored with their pricing version and cost basis (provider-reported charge vs estimate vs simulated vs zero-invoice local). Failed requests may carry partial or unknown usage; unknown stays unknown and is flagged for reconciliation.

## Consequences
Usage and cost figures are auditable and honestly labelled in the dashboard and reports; no figure is presented as real billing unless a provider actually reported it. Cost: consumers of the data must handle the unknown case, and the UI must display provenance rather than one clean number.
