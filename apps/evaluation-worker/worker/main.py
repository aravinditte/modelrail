"""Evaluation worker: polls for pending EvaluationRun rows and executes them
with the shared gateway evaluation service. Separate process, same database.
A worker crash leaves the run in 'running'; the run can be re-queued by
setting it back to 'pending' (see runbooks/failed-evaluations.md).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

GATEWAY_DIR = Path(os.environ.get("MODELRAIL_GATEWAY_DIR", "apps/gateway"))
REPO_ROOT = Path(os.environ.get("MODELRAIL_REPO_ROOT", "."))
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.models import EvaluationRun  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from app.services.evaluation_service import execute_run  # noqa: E402

POLL_S = float(os.environ.get("EVAL_WORKER_POLL_S", "3"))


def main() -> None:
    init_db()
    factory = get_session_factory()
    print("modelrail evaluation worker started", flush=True)
    while True:
        session = factory()
        try:
            run = session.execute(
                select(EvaluationRun)
                .where(EvaluationRun.status == "pending")
                .order_by(EvaluationRun.id)
                .limit(1)
            ).scalar_one_or_none()
            if run is not None:
                print(f"executing evaluation run {run.id}", flush=True)
                execute_run(session, run)
            else:
                time.sleep(POLL_S)
        finally:
            session.close()


if __name__ == "__main__":
    main()
