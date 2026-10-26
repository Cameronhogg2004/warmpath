"""What each agent must hand back. Structured outputs, so code can check them."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TieType = Literal["clinical_trial", "co_publication", "named_chair", "web_source"]


class Tie(BaseModel):
    type: TieType
    description: str = Field(description="One sentence: what links this person to the company, specifically.")
    year: int | None = Field(None, description="Year of the tie (trial start, paper year), if known.")
    source_ids: list[str] = Field(default_factory=list, description="Source ids (S1, S2...) from tool results. Web ties: empty.")
    web_url: str | None = Field(None, description="Only for web_source ties: the page that states the tie.")


class Candidate(BaseModel):
    name: str = Field(description="Full name as written in the source.")
    yale_role: str = Field("", description="Their Yale title, if a tool showed it.")
    ties: list[Tie]
    company_counterparts: list[str] = Field(default_factory=list,
                                            description="Company-side people named in the same sources.")


class ScoutReport(BaseModel):
    candidates: list[Candidate] = Field(description="At most 8 people, strongest ties first.")
    notes: str = Field("", description="One or two sentences on what was searched and not found.")


class Verdict(BaseModel):
    candidate_id: str
    supported: bool = Field(description="The evidence shows this person has the stated tie to the company.")
    current: bool = Field(description="The tie is ongoing or from the last three years.")
    reason: str = Field(description="One short sentence.")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


class RankedIntroducer(BaseModel):
    candidate_id: str
    strength: Literal["strong", "medium", "weak"]
    why: str = Field(description="One or two sentences, citing [S#] ids.")
    ask: str = Field(description="What to ask this person for, in one sentence.")


class Briefing(BaseModel):
    headline: str = Field(description="One line: the best route into the company.")
    summary: list[str] = Field(description="Two to four short bullets, citing [S#] ids.")
    introducers: list[RankedIntroducer]
    email_subject: str
    email_body: str = Field(description="A short note to the top introducer asking for an introduction. "
                                        "No email addresses or links. Sign off as [Your name].")
    gaps: list[str] = Field(default_factory=list, description="What could not be confirmed, and what to check next.")
