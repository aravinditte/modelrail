"""Render an evaluation report dict to a Markdown summary (stdlib only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict) -> str:
    config = report.get("config") or {}
    op = report.get("operational") or {}
    latency = op.get("latency_ms") or {}
    per_category = report.get("per_category") or report.get("categories") or {}

    lines: List[str] = []
    lines.append("# ModelRail Evaluation Report")
    lines.append("")
    lines.append(f"- Dataset version: `{report.get('dataset_version', '-')}`")
    lines.append(f"- Model: `{config.get('model', '-')}`")
    lines.append(f"- Mode: `{config.get('mode', '-')}`")
    lines.append("")
    lines.append("## Operational metrics")
    lines.append("")
    lines.append(f"- Total cases: {op.get('total_cases', '-')}")
    lines.append(f"- Success rate: {_fmt(op.get('success_rate'))} " f"(errors: {op.get('error_count', '-')})")
    lines.append(
        f"- Latency ms: p50 {_fmt(latency.get('p50'), 2)}, "
        f"p95 {_fmt(latency.get('p95'), 2)}, mean {_fmt(latency.get('mean'), 2)}"
    )
    lines.append(
        f"- Tokens: input {op.get('total_input_tokens', '-')}, "
        f"output {op.get('total_output_tokens', '-')}"
    )
    lines.append(f"- Estimated cost (USD): {_fmt(op.get('estimated_cost_usd'), 6)}")
    lines.append("")
    lines.append("## Per-category metrics")
    lines.append("")
    for category, metrics in sorted(per_category.items()):
        lines.append(f"### {category} (n={metrics.get('count', '-')})")
        lines.append("")
        for key, value in sorted(metrics.items()):
            if key in ("count", "per_label"):
                continue
            lines.append(f"- {key}: {_fmt(value)}")
        per_label = metrics.get("per_label")
        if per_label:
            lines.append("- per-label F1:")
            for label, vals in sorted(per_label.items()):
                lines.append(f"  - {label}: {_fmt(vals.get('f1'))}")
        lines.append("")

    failed = [
        r for r in (report.get("results") or report.get("per_case") or []) if r.get("status") != "success"
    ]
    lines.append("## Errors")
    lines.append("")
    if failed:
        for result in failed:
            lines.append(f"- `{result.get('id')}`: {result.get('error')}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


# Descriptive alias.
render_report_markdown = render_markdown
report_to_markdown = render_markdown


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="modelrail_evals.reporting")
    parser.add_argument("--report", required=True, help="Report JSON path")
    parser.add_argument("--out", default=None, help="Markdown output path (default: stdout)")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    markdown = render_markdown(report)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
