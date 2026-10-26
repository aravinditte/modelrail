"""ModelRail evaluation framework: datasets, metrics, runner, regression gate."""

from .dataset import CASE_VERSION, CATEGORIES, DATASET_VERSION, Case, load_dataset, validate_cases
from .gate import DEFAULT_THRESHOLDS, compare_reports
from .metrics import (
    classification_metrics,
    estimate_tokens,
    extraction_metrics,
    instruction_metrics,
    safety_metrics,
)
from .reporting import render_markdown
from .runner import run_evaluation, scripted_model

__version__ = "1.0.0"
__all__ = [
    "CASE_VERSION",
    "CATEGORIES",
    "DATASET_VERSION",
    "DEFAULT_THRESHOLDS",
    "Case",
    "classification_metrics",
    "compare_reports",
    "estimate_tokens",
    "extraction_metrics",
    "instruction_metrics",
    "load_dataset",
    "render_markdown",
    "run_evaluation",
    "safety_metrics",
    "scripted_model",
    "validate_cases",
]
