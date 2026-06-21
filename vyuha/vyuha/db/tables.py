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


# ── FutureAGI-parity tables ───────────────────────────────────────────────────

class DatasetRow(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4())[:8].upper())
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="build")
    column_types: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items: Mapped[list["DatasetItemRow"]] = relationship("DatasetItemRow", back_populates="dataset", lazy="select")


class DatasetItemRow(Base):
    __tablename__ = "dataset_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped["DatasetRow"] = relationship("DatasetRow", back_populates="items")


class TraceRow(Base):
    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    input_: Mapped[dict | None] = mapped_column("input", JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    spans: Mapped[list["SpanRow"]] = relationship("SpanRow", back_populates="trace", lazy="select")


class SpanRow(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str] = mapped_column(String(64), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    span_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="llm")
    operation_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_: Mapped[dict | None] = mapped_column("input", JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OK")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    trace: Mapped["TraceRow"] = relationship("TraceRow", back_populates="spans")


class PromptTemplateRow(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    folder: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["PromptVersionRow"]] = relationship(
        "PromptVersionRow",
        back_populates="template",
        lazy="select",
        order_by="PromptVersionRow.version_number",
    )


class PromptVersionRow(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id: Mapped[str] = mapped_column(String(64), ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    template: Mapped["PromptTemplateRow"] = relationship("PromptTemplateRow", back_populates="versions")


class AlertMonitorRow(Base):
    __tablename__ = "alert_monitors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_operator: Mapped[str] = mapped_column(String(16), nullable=False, default="less_than")
    warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    notification_emails: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentDefinitionRow(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    voice_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnnotationQueueRow(Base):
    __tablename__ = "annotation_queues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    annotations_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    labels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    annotation_items: Mapped[list["AnnotationItemRow"]] = relationship("AnnotationItemRow", back_populates="queue", lazy="select")


class AnnotationItemRow(Base):
    __tablename__ = "annotation_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id: Mapped[str] = mapped_column(String(64), ForeignKey("annotation_queues.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    annotations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    queue: Mapped["AnnotationQueueRow"] = relationship("AnnotationQueueRow", back_populates="annotation_items")
