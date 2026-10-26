"""Evaluation runner for ModelRail.

Runs dataset cases against a model callable and produces a report dict.
The built-in scripted model is deterministic:

- mode ``"good"``     -> returns ``case.mock_output``
- mode ``"degraded"`` -> returns ``case.degraded_output``

Any other callable may be supplied: it is called with the :class:`Case`
object and may return a string, or raise (recorded as an error case).

CLI::

    python -m modelrail_evals.runner --dataset <path> \
        --mode good|degraded --out <report.json>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from .dataset import DATASET_VERSION, Case, load_dataset
from .metrics import (
    classification_metrics,
    estimate_tokens,
    extraction_metrics,
    instruction_metrics,
    safety_metrics,
)

# Configured (fictional, local) prices used only for cost *estimates*.
INPUT_COST_PER_1K_TOKENS_USD = 0.001
OUTPUT_COST_PER_1K_TOKENS_USD = 0.002
PRICING_VERSION = "mock-pricing-v1"


def scripted_model(mode: str) -> Callable[[Case], str]:
    """Return the deterministic scripted model function for ``mode``."""
    if mode not in ("good", "degraded"):
        raise ValueError(f"unknown mode {mode!r}; expected 'good' or 'degraded'")

    def _model(case: Case) -> str:
        return case.mock_output if mode == "good" else case.degraded_output

    _model.__name__ = f"scripted-{mode}"
    return _model


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _call_model(model_fn: Callable, case: Case) -> str:
    """Call model_fn flexibly: Case first, then input text as a fallback."""
    try:
        result = model_fn(case)
    except TypeError:
        result = model_fn(case.input)
    if not isinstance(result, str):
        result = str(result)
    return result


def _per_case_metrics(case: Case, output: str) -> dict:
    if case.category == "extraction":
        return extraction_metrics(case.expected, output)
    if case.category == "instruction_following":
        return instruction_metrics(output, case.checks)
    if case.category == "safety":
        return safety_metrics(output, case.expected, case.checks)
    if case.category == "classification":
        predicted = output.strip()
        return {"correct": predicted == case.expected.strip(), "predicted": predicted}
    return {}


def run_evaluation(
    cases: List[Case],
    model_fn: Optional[Callable] = None,
    *,
    mode: str = "good",
    model_name: str = "scripted-mock",
    dataset_version: str = DATASET_VERSION,
) -> dict:
    """Run ``cases`` against ``model_fn`` (or the scripted model) -> report dict."""
    if model_fn is None:
        model_fn = scripted_model(mode)
        config_mode = mode
    else:
        config_mode = mode if mode else "custom"

    per_case: List[dict] = []
    latencies_ms: List[float] = []
    errors = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for case in cases:
        start = time.perf_counter()
        status = "success"
        error: Optional[str] = None
        output = ""
        try:
            output = _call_model(model_fn, case)
        except Exception as exc:  # recorded, not raised: a run reports errors
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            errors += 1
        latency_ms = (time.perf_counter() - start) * 1000.0
        latencies_ms.append(latency_ms)

        input_tokens = estimate_tokens(case.input)
        output_tokens = estimate_tokens(output) if status == "success" else 0
        cost = (
            input_tokens / 1000.0 * INPUT_COST_PER_1K_TOKENS_USD
            + output_tokens / 1000.0 * OUTPUT_COST_PER_1K_TOKENS_USD
        )
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cost += cost

        metrics = _per_case_metrics(case, output) if status == "success" else {}
        per_case.append(
            {
                "id": case.id,
                "category": case.category,
                "status": status,
                "error": error,
                "output": output,
                "expected": case.expected,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": cost,
                "metrics": metrics,
            }
        )

    total = len(cases)
    per_category = _aggregate(per_case)
    operational = {
        "total_cases": total,
        "success_count": total - errors,
        "error_count": errors,
        "success_rate": (total - errors) / total if total else 0.0,
        "error_rate": errors / total if total else 0.0,
        "latency_ms": {
            "p50": _percentile(latencies_ms, 50),
            "p95": _percentile(latencies_ms, 95),
            "mean": (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0,
            "min": min(latencies_ms) if latencies_ms else 0.0,
            "max": max(latencies_ms) if latencies_ms else 0.0,
        },
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "estimated_cost_usd": total_cost,
        "pricing_version": PRICING_VERSION,
    }
    return {
        "dataset_version": dataset_version,
        "config": {"mode": config_mode, "model": model_name},
        "per_category": per_category,
        "categories": per_category,  # alias for convenience
        "operational": operational,
        "results": per_case,
        "per_case": per_case,  # alias for convenience
    }


def _aggregate(per_case: List[dict]) -> dict:
    by_cat: dict = {}
    for result in per_case:
        by_cat.setdefault(result["category"], []).append(result)

    agg: dict = {}
    for category, results in sorted(by_cat.items()):
        ok = [r for r in results if r["status"] == "success"]
        entry: dict = {"count": len(results), "errors": len(results) - len(ok)}
        if category == "extraction" and ok:
            entry["json_validity_rate"] = sum(1 for r in ok if r["metrics"].get("json_valid")) / len(ok)
            entry["field_exact_match"] = sum(r["metrics"].get("field_exact_match", 0.0) for r in ok) / len(ok)
            entry["completeness"] = sum(r["metrics"].get("completeness", 0.0) for r in ok) / len(ok)
        elif category == "instruction_following" and ok:
            entry["pass_rate"] = sum(1 for r in ok if r["metrics"].get("passed")) / len(ok)
            entry["constraint_satisfaction"] = sum(
                r["metrics"].get("constraint_satisfaction", 0.0) for r in ok
            ) / len(ok)
        elif category == "classification":
            pairs = [(r["expected"], r["metrics"].get("predicted", "")) for r in ok]
            entry.update(classification_metrics(pairs))
        elif category == "safety" and ok:
            entry["behaviour_correct_rate"] = sum(
                1 for r in ok if r["metrics"].get("behaviour_correct")
            ) / len(ok)
            entry["refusal_accuracy"] = entry["behaviour_correct_rate"]
            entry["safe_rate"] = sum(1 for r in ok if r["metrics"].get("safe")) / len(ok)
            entry["disclosure_rate"] = sum(1 for r in ok if r["metrics"].get("disclosed_forbidden")) / len(ok)
        agg[category] = entry
    return agg


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="modelrail_evals.runner")
    parser.add_argument("--dataset", required=True, help="Path to dataset .jsonl")
    parser.add_argument("--mode", choices=("good", "degraded"), default="good")
    parser.add_argument("--model", default="scripted-mock", help="Model name recorded in the report config")
    parser.add_argument("--out", required=True, help="Where to write the report JSON")
    args = parser.parse_args(argv)

    cases = load_dataset(args.dataset)
    report = run_evaluation(cases, mode=args.mode, model_name=args.model)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {out_path} ({report['operational']['total_cases']} cases, " f"mode={args.mode})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
