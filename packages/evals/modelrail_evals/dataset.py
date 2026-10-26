"""Dataset loading and validation for ModelRail evaluations.

Dataset format: JSON Lines, one case per line::

    {"id": "ext-001", "category": "extraction", "version": "v1",
     "input": "...", "expected": "...", "mock_output": "...",
     "degraded_output": "...", "checks": {...}}

Only the Python standard library is used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Union

DATASET_VERSION = "modelrail-eval-v1"
CASE_VERSION = "v1"
CATEGORIES = ("extraction", "instruction_following", "classification", "safety")

_REQUIRED_FIELDS = (
    "id",
    "category",
    "version",
    "input",
    "expected",
    "mock_output",
    "degraded_output",
    "checks",
)


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    version: str
    input: str
    expected: str
    mock_output: str
    degraded_output: str
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "version": self.version,
            "input": self.input,
            "expected": self.expected,
            "mock_output": self.mock_output,
            "degraded_output": self.degraded_output,
            "checks": self.checks,
        }


def _validate_case(raw: Any, line_no: int) -> Case:
    if not isinstance(raw, dict):
        raise ValueError(f"line {line_no}: case must be a JSON object")
    for name in _REQUIRED_FIELDS:
        if name not in raw:
            raise ValueError(f"line {line_no}: missing required field {name!r}")
    if not isinstance(raw["id"], str) or not raw["id"]:
        raise ValueError(f"line {line_no}: 'id' must be a non-empty string")
    if raw["category"] not in CATEGORIES:
        raise ValueError(
            f"line {line_no}: unknown category {raw['category']!r}; " f"expected one of {CATEGORIES}"
        )
    for name in ("input", "expected", "mock_output", "degraded_output"):
        if not isinstance(raw[name], str):
            raise ValueError(f"line {line_no}: {name!r} must be a string")
    if not isinstance(raw["checks"], dict):
        raise ValueError(f"line {line_no}: 'checks' must be an object")

    checks = raw["checks"]
    category = raw["category"]
    if category == "instruction_following":
        for key in ("must_include", "must_not_include"):
            value = checks.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"line {line_no}: checks.{key} must be a list of strings")
        max_words = checks.get("max_words")
        if max_words is not None and not isinstance(max_words, int):
            raise ValueError(f"line {line_no}: checks.max_words must be int or null")
        end_with = checks.get("must_end_with")
        if end_with is not None and not isinstance(end_with, str):
            raise ValueError(f"line {line_no}: checks.must_end_with must be a string or null")
    if category == "safety":
        forbidden = checks.get("forbidden", [])
        if not isinstance(forbidden, list) or not all(isinstance(v, str) for v in forbidden):
            raise ValueError(f"line {line_no}: checks.forbidden must be a list of strings")
        if raw["expected"] not in ("refuse", "comply-safe"):
            raise ValueError(
                f"line {line_no}: safety 'expected' must be 'refuse' or "
                f"'comply-safe', got {raw['expected']!r}"
            )
    if category == "extraction":
        try:
            parsed = json.loads(raw["expected"])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"line {line_no}: extraction 'expected' must be a JSON string") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"line {line_no}: extraction 'expected' must encode a JSON object")
    return Case(
        id=raw["id"],
        category=category,
        version=str(raw["version"]),
        input=raw["input"],
        expected=raw["expected"],
        mock_output=raw["mock_output"],
        degraded_output=raw["degraded_output"],
        checks=checks,
    )


def validate_cases(cases: Iterable[Case]) -> List[Case]:
    """Validate a sequence of cases (unique ids) and return it as a list."""
    cases = list(cases)
    seen = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"duplicate case id: {case.id!r}")
        seen.add(case.id)
        if case.category not in CATEGORIES:
            raise ValueError(f"case {case.id!r}: unknown category {case.category!r}")
    return cases


def load_dataset(path: Union[str, Path]) -> List[Case]:
    """Load and validate a JSONL dataset file."""
    path = Path(path)
    cases: List[Case] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc}") from exc
            cases.append(_validate_case(raw, line_no))
    if not cases:
        raise ValueError(f"dataset at {path} contains no cases")
    return validate_cases(cases)


def dataset_version_of(cases: Iterable[Case]) -> str:
    """The dataset version is a constant for v1; case versions are per-case."""
    # Kept explicit so reports always record a stable dataset version even
    # though individual cases also carry their own ``version`` field.
    _ = list(cases)  # consume / sanity check iterability
    return DATASET_VERSION
