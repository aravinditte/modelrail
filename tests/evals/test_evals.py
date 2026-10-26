"""Tests for the ModelRail evaluation framework.

Run with:
    PYTHONPATH=packages/evals pytest tests/evals -q
(from the repository root)
"""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "packages" / "evals" / "datasets" / "modelrail-eval-v1.jsonl"
EVALS_PATH = REPO_ROOT / "packages" / "evals"

from modelrail_evals.dataset import load_dataset  # noqa: E402
from modelrail_evals.gate import compare_reports  # noqa: E402
from modelrail_evals.metrics import (  # noqa: E402
    classification_metrics,
    extraction_metrics,
    instruction_metrics,
    safety_metrics,
)
from modelrail_evals.reporting import render_markdown  # noqa: E402
from modelrail_evals.runner import run_evaluation  # noqa: E402


@pytest.fixture(scope="module")
def cases():
    return load_dataset(DATASET_PATH)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
def test_dataset_has_exactly_100_cases_with_right_distribution(cases):
    assert len(cases) == 100
    counts = Counter(c.category for c in cases)
    assert counts == {
        "extraction": 30,
        "instruction_following": 25,
        "classification": 25,
        "safety": 20,
    }


def test_dataset_has_dev_and_held_out_splits(cases):
    splits = Counter(c.split for c in cases)
    assert splits["dev"] == 70
    assert splits["held_out"] == 30
    dev_cases = load_dataset(DATASET_PATH, split="dev")
    held_out_cases = load_dataset(DATASET_PATH, split="held_out")
    assert len(dev_cases) == 70
    assert len(held_out_cases) == 30


def test_dataset_ids_unique(cases):
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_dataset_cases_have_required_fields(cases):
    for case in cases:
        assert case.input
        assert case.expected
        assert case.mock_output
        assert case.degraded_output
        assert isinstance(case.checks, dict)
        assert case.version


def test_extraction_expected_and_mock_are_json_objects(cases):
    for case in cases:
        if case.category == "extraction":
            assert isinstance(json.loads(case.expected), dict)
            assert isinstance(json.loads(case.mock_output), dict)


# ---------------------------------------------------------------------------
# Metrics correctness on hand-made examples
# ---------------------------------------------------------------------------
def test_extraction_metrics_perfect():
    m = extraction_metrics('{"a": 1, "b": "x"}', '{"a": 1, "b": "x"}')
    assert m == {"json_valid": True, "field_exact_match": 1.0, "completeness": 1.0}


def test_extraction_metrics_missing_and_wrong_fields():
    m = extraction_metrics('{"a": 1, "b": "x", "c": 3}', '{"a": 1, "b": "y"}')
    assert m["json_valid"] is True
    assert m["completeness"] == pytest.approx(2 / 3)
    assert m["field_exact_match"] == pytest.approx(1 / 3)


def test_extraction_metrics_invalid_json():
    m = extraction_metrics('{"a": 1}', '{"a": ')
    assert m == {"json_valid": False, "field_exact_match": 0.0, "completeness": 0.0}


def test_instruction_metrics_pass_and_fail():
    checks = {
        "must_include": ["solar"],
        "must_not_include": ["coal"],
        "max_words": 5,
        "must_end_with": ".",
    }
    ok = instruction_metrics("Solar power is clean.", checks)
    assert ok["passed"] is True
    assert ok["constraint_satisfaction"] == 1.0

    bad = instruction_metrics("Coal and more words here than allowed today", checks)
    assert bad["passed"] is False
    assert bad["constraint_satisfaction"] < 0.5


def test_classification_metrics_handmade():
    pairs = [
        ("billing", "billing"),
        ("billing", "technical"),
        ("technical", "technical"),
        ("technical", "technical"),
    ]
    m = classification_metrics(pairs)
    assert m["accuracy"] == pytest.approx(0.75)
    # billing: P=1.0 (no FP), R=0.5 -> F1=2/3 ; technical: P=2/3, R=1.0 -> F1=0.8
    assert m["per_label"]["billing"]["f1"] == pytest.approx(2 / 3)
    assert m["per_label"]["technical"]["f1"] == pytest.approx(0.8)
    assert m["macro_f1"] == pytest.approx((2 / 3 + 0.8) / 2)
    assert m["macro_precision"] == pytest.approx((1.0 + 2 / 3) / 2)
    assert m["macro_recall"] == pytest.approx((0.5 + 1.0) / 2)


def test_classification_metrics_perfect():
    pairs = [("a", "a"), ("b", "b"), ("a", "a")]
    m = classification_metrics(pairs)
    assert m["accuracy"] == 1.0
    assert m["macro_f1"] == 1.0


def test_safety_metrics_refusal_and_disclosure():
    ok = safety_metrics("I can't help with that request.", "refuse", {"forbidden": ["FAKE-SECRET-123"]})
    assert ok["safe"] is True
    assert ok["behaviour_correct"] is True
    assert ok["disclosed_forbidden"] is False

    leak = safety_metrics("Sure: FAKE-SECRET-123", "refuse", {"forbidden": ["FAKE-SECRET-123"]})
    assert leak["safe"] is False
    assert leak["disclosed_forbidden"] is True
    assert leak["disclosed_strings"] == ["FAKE-SECRET-123"]

    benign_ok = safety_metrics(
        "Use a password manager to store unique passwords.",
        "comply-safe",
        {"forbidden": ["FAKE-SECRET-123"]},
    )
    assert benign_ok["safe"] is True

    benign_refused = safety_metrics("I can't help with that request.", "comply-safe", {"forbidden": []})
    assert benign_refused["safe"] is False


# ---------------------------------------------------------------------------
# Runner + gate
# ---------------------------------------------------------------------------
def _comparable_metrics(report):
    """Report metrics that must be reproducible (latency excluded: it is
    measured wall-clock time and necessarily varies between runs)."""
    return {
        "dataset_version": report["dataset_version"],
        "config": report["config"],
        "per_category": report["per_category"],
        "success_rate": report["operational"]["success_rate"],
        "error_rate": report["operational"]["error_rate"],
        "total_input_tokens": report["operational"]["total_input_tokens"],
        "total_output_tokens": report["operational"]["total_output_tokens"],
        "estimated_cost_usd": report["operational"]["estimated_cost_usd"],
        "outputs": [r["output"] for r in report["results"]],
    }


def test_good_mode_reproduces_identical_metrics_twice(cases):
    first = run_evaluation(cases, mode="good")
    second = run_evaluation(cases, mode="good")
    assert _comparable_metrics(first) == _comparable_metrics(second)


def test_good_mode_scores_are_perfect(cases):
    report = run_evaluation(cases, mode="good")
    assert report["operational"]["error_rate"] == 0.0
    assert report["per_category"]["extraction"]["json_validity_rate"] == 1.0
    assert report["per_category"]["classification"]["macro_f1"] == 1.0
    assert report["per_category"]["instruction_following"]["pass_rate"] == 1.0
    assert report["per_category"]["safety"]["safe_rate"] == 1.0
    assert report["per_category"]["safety"]["disclosure_rate"] == 0.0
    assert report["operational"]["latency_ms"]["p95"] >= report["operational"]["latency_ms"]["p50"] >= 0.0


def test_custom_callable_is_accepted(cases):
    report = run_evaluation(cases[:4], model_fn=lambda case: case.mock_output, mode="custom")
    assert report["operational"]["total_cases"] == 4
    assert report["operational"]["error_count"] == 0


def test_degraded_run_fails_gate_against_good_baseline(cases):
    baseline = run_evaluation(cases, mode="good")
    candidate = run_evaluation(cases, mode="degraded")
    # Degraded output is measurably worse on the headline metrics.
    assert (
        candidate["per_category"]["extraction"]["json_validity_rate"]
        < baseline["per_category"]["extraction"]["json_validity_rate"]
    )
    assert (
        candidate["per_category"]["classification"]["macro_f1"]
        < baseline["per_category"]["classification"]["macro_f1"]
    )
    assert (
        candidate["per_category"]["safety"]["disclosure_rate"]
        > baseline["per_category"]["safety"]["disclosure_rate"]
    )
    passed, failures = compare_reports(baseline, candidate)
    assert passed is False
    assert failures  # non-empty, human-readable reasons


def test_good_vs_good_passes_gate(cases):
    baseline = run_evaluation(cases, mode="good")
    candidate = run_evaluation(cases, mode="good")
    passed, failures = compare_reports(baseline, candidate)
    assert passed is True, failures
    assert failures == []


def test_reporting_renders_markdown(cases):
    report = run_evaluation(cases, mode="good")
    md = render_markdown(report)
    assert "# ModelRail Evaluation Report" in md
    assert "modelrail-eval-v1" in md
    assert "extraction" in md


# ---------------------------------------------------------------------------
# CLIs
# ---------------------------------------------------------------------------
def _run_cli(args, cwd):
    env = {"PYTHONPATH": str(EVALS_PATH), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_runner_and_gate_clis(tmp_path):
    good = tmp_path / "good.json"
    degraded = tmp_path / "degraded.json"
    result = _run_cli(
        ["modelrail_evals.runner", "--dataset", str(DATASET_PATH), "--mode", "good", "--out", str(good)],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    result = _run_cli(
        [
            "modelrail_evals.runner",
            "--dataset",
            str(DATASET_PATH),
            "--mode",
            "degraded",
            "--out",
            str(degraded),
        ],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    ok = _run_cli(
        ["modelrail_evals.gate", "--baseline", str(good), "--candidate", str(good)],
        cwd=REPO_ROOT,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr

    bad = _run_cli(
        ["modelrail_evals.gate", "--baseline", str(good), "--candidate", str(degraded)],
        cwd=REPO_ROOT,
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "GATE FAILED" in bad.stdout
