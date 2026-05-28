"""
SQLAlchemy ORM table definitions.
Pydantic models ↔ ORM rows are bridged by the repository layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum as SAEnum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TestCaseRow(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    pass_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(256), nullable=False, default="AUTO_GENERATED")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    linked_production_call: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Nested JSON blobs — these are Pydantic model serializations
    persona_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    conversation_graph: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tool_call_sequence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ground_truth_end_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    runs: Mapped[list[RunRow]] = relationship("RunRow", back_populates="test_case", lazy="select")

    @property
    def language(self) -> str:
        return self.persona_config.get("language", "en-IN")


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_case_id: Mapped[str] = mapped_column(String(64), ForeignKey("test_cases.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", index=True)
    judge_model_used: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scores — stored flat for easy querying
    eva_a_task_completion: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_a_faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_a_speech_fidelity: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_a_composite: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    eva_x_conciseness: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_x_progression: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_x_turn_taking: Mapped[float | None] = mapped_column(Float, nullable=True)
    eva_x_composite: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Diagnostics
    latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full detail blobs
    turns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    final_db_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    test_case: Mapped[TestCaseRow] = relationship("TestCaseRow", back_populates="runs")


class PassKRow(Base):
    __tablename__ = "pass_k_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_case_id: Mapped[str] = mapped_column(String(64), ForeignKey("test_cases.id"), nullable=False, index=True)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    pass_all_k: Mapped[float] = mapped_column(Float, nullable=False)
    mean_eva_a: Mapped[float] = mapped_column(Float, nullable=False)
    mean_eva_x: Mapped[float] = mapped_column(Float, nullable=False)
    run_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
