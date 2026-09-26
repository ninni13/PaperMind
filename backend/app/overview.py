"""Shared schemas for overview content and API responses."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=1800)]
Item = Annotated[str, Field(min_length=1, max_length=700)]


class PaperOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_question: Text | None
    method: Text | None
    datasets: list[Item] = Field(max_length=16)
    key_results: list[Item] = Field(max_length=10)
    limitations: list[Item] = Field(max_length=10)


class OverviewResponse(BaseModel):
    paper_id: int
    status: Literal["not_generated", "ready"]
    overview: PaperOverview | None = None
    generated_at: datetime | None = None
    model: str | None = None
    schema_version: int | None = None
    context_chunks: int | None = None
    context_pages: int | None = None
