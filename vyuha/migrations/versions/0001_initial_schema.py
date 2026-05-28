"""Initial schema: test_cases, runs, pass_k_results

Revision ID: 0001
Revises:
Create Date: 2026-05-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("user_goal", sa.Text, nullable=False),
        sa.Column("pass_criteria", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(256), nullable=False, server_default="AUTO_GENERATED"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("linked_production_call", sa.String(256), nullable=True),
        sa.Column("persona_config", JSONB, nullable=False),
        sa.Column("conversation_graph", JSONB, nullable=False),
        sa.Column("tool_call_sequence", JSONB, nullable=False, server_default="[]"),
        sa.Column("ground_truth_end_state", JSONB, nullable=False, server_default="{}"),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_test_cases_category", "test_cases", ["category"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("test_case_id", sa.String(64), sa.ForeignKey("test_cases.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verdict", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("judge_model_used", sa.String(64), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("eva_a_task_completion", sa.Float, nullable=True),
        sa.Column("eva_a_faithfulness", sa.Float, nullable=True),
        sa.Column("eva_a_speech_fidelity", sa.Float, nullable=True),
        sa.Column("eva_a_composite", sa.Float, nullable=True),
        sa.Column("eva_x_conciseness", sa.Float, nullable=True),
        sa.Column("eva_x_progression", sa.Float, nullable=True),
        sa.Column("eva_x_turn_taking", sa.Float, nullable=True),
        sa.Column("eva_x_composite", sa.Float, nullable=True),
        sa.Column("latency_p50_ms", sa.Float, nullable=True),
        sa.Column("latency_p95_ms", sa.Float, nullable=True),
        sa.Column("turns", JSONB, nullable=False, server_default="[]"),
        sa.Column("final_db_state", JSONB, nullable=False, server_default="{}"),
        sa.Column("failure_report", JSONB, nullable=True),
    )
    op.create_index("ix_runs_test_case_id", "runs", ["test_case_id"])
    op.create_index("ix_runs_verdict", "runs", ["verdict"])
    op.create_index("ix_runs_eva_a_composite", "runs", ["eva_a_composite"])

    op.create_table(
        "pass_k_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("test_case_id", sa.String(64), sa.ForeignKey("test_cases.id"), nullable=False),
        sa.Column("k", sa.Integer, nullable=False),
        sa.Column("pass_at_k", sa.Float, nullable=False),
        sa.Column("pass_all_k", sa.Float, nullable=False),
        sa.Column("mean_eva_a", sa.Float, nullable=False),
        sa.Column("mean_eva_x", sa.Float, nullable=False),
        sa.Column("run_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pass_k_test_case_id", "pass_k_results", ["test_case_id"])


def downgrade() -> None:
    op.drop_table("pass_k_results")
    op.drop_table("runs")
    op.drop_table("test_cases")
