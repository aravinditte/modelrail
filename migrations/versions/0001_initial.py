"""Initial schema: create all ModelRail tables from the declarative metadata.

Using the metadata in the initial migration keeps the migration and the ORM
in lockstep for the first release; subsequent changes get hand-written
migrations.

Revision ID: 0001_initial
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "gateway"))

from alembic import op  # noqa: E402
from app.db.models import Base  # noqa: E402

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
