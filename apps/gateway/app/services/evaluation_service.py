"""Bridge between EvaluationRun rows and the packages/evals framework.

Mode semantics for the built-in deterministic demo: a model name containing
"degraded" runs the framework's degraded scripted model; anything else runs
the good scripted model. Reports stored on the run are sanitised — raw model
outputs are not persisted in the summary, only metrics and failed case IDs.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import metrics
from ..db.models import EvaluationResult, EvaluationRun


def _mode_for(model_name: str) -> str:
    return "degraded" if "degraded" in (model_name or "").lower() else "good"


def _load_framework():
    package_path = Path(get_settings().eval_package_path)
    if str(package_path) not in sys.path:
        sys.path.insert(0, str(package_path))
    from modelrail_evals import gate as gate_module
    from modelrail_evals import runner as runner_module
    from modelrail_evals.dataset import load_dataset

    return load_dataset, runner_module, gate_module


def _sanitise(report: dict) -> dict:
    failed_ids = [r["id"] for r in report.get("results", []) if r.get("status") != "success"]
    return {
        "dataset_version": report.get("dataset_version"),
        "config": report.get("config"),
        "per_category": report.get("per_category"),
        "operational": report.get("operational"),
        "failed_case_ids": failed_ids,
    }


def execute_run(db: Session, run: EvaluationRun) -> EvaluationRun:
    load_dataset, runner_module, gate_module = _load_framework()
    started = time.monotonic()
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.commit()
    try:
        cases = load_dataset(get_settings().eval_dataset_path)
        baseline_report = runner_module.run_evaluation(
            cases,
            mode=_mode_for(run.baseline_model),
            model_name=run.baseline_model,
            dataset_version=run.dataset_version,
        )
        candidate_report = runner_module.run_evaluation(
            cases,
            mode=_mode_for(run.candidate_model),
            model_name=run.candidate_model,
            dataset_version=run.dataset_version,
        )
        passed, failures = gate_module.compare_reports(baseline_report, candidate_report)
        # persist sanitised per-case results for the candidate
        db.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).delete()
        for result in candidate_report.get("results", []):
            m = result.get("metrics") or {}
            case_failed = (
                result.get("status") != "success"
                or m.get("correct") is False
                or ("passed" in m and m.get("passed") is False)
                or ("safe" in m and m.get("safe") is False)
                or ("json_valid" in m and m.get("json_valid") is False)
            )
            db.add(
                EvaluationResult(
                    run_id=run.id,
                    case_id=result["id"],
                    metric_values=m,
                    latency_ms=int(result.get("latency_ms") or 0),
                    input_tokens=result.get("input_tokens"),
                    output_tokens=result.get("output_tokens"),
                    cost=result.get("estimated_cost_usd"),
                    status="failed" if case_failed else "passed",
                    failure_reason=result.get("error"),
                )
            )
        run.summary = {
            "baseline": _sanitise(baseline_report),
            "candidate": _sanitise(candidate_report),
            "gate": {"passed": passed, "failures": failures},
            "dataset_version": run.dataset_version,
            "configuration_version": run.configuration_version,
        }
        run.status = "completed"
        metrics.EVAL_RUNS.labels(status="completed").inc()
    except Exception as exc:  # recorded on the run, never silently swallowed
        run.status = "failed"
        run.summary = {"error": f"{type(exc).__name__}: {exc}"}
        metrics.EVAL_RUNS.labels(status="failed").inc()
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    metrics.EVAL_DURATION.observe(time.monotonic() - started)
    db.refresh(run)
    return run
