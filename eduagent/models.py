from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"


class KnowledgeUse(BaseModel):
    concept: str
    status: MatchStatus
    node_ids: list[str] = Field(default_factory=list)
    evidence: str
    unmapped_candidate: str | None = None

    @model_validator(mode="after")
    def validate_match(self):
        if self.status == MatchStatus.MATCHED and len(self.node_ids) != 1:
            raise ValueError("MATCHED requires exactly one node ID")
        if self.status == MatchStatus.UNMAPPED and self.node_ids:
            raise ValueError("UNMAPPED cannot contain node IDs")
        if self.status == MatchStatus.AMBIGUOUS and len(self.node_ids) < 2:
            raise ValueError("AMBIGUOUS requires at least two candidates")
        return self


class Step(BaseModel):
    step_id: str
    content: str


class Solution(BaseModel):
    solution_id: str
    name: str
    steps: list[Step] = Field(min_length=1)
    final_result: str

    @model_validator(mode="after")
    def unique_steps(self):
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate step IDs")
        return self


class GeneratedSolutions(BaseModel):
    solutions: list[Solution] = Field(max_length=3)

    @model_validator(mode="after")
    def unique_solutions(self):
        ids = [s.solution_id for s in self.solutions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate solution IDs")
        return self


class BaselineAResult(BaseModel):
    methods: list[str]
    reason: str


class BaselineBResult(BaseModel):
    selected_solution_ids: list[str]
    reason: str


class StepAnnotation(BaseModel):
    step_id: str
    content: str
    knowledge: list[KnowledgeUse]


class SolutionAnnotation(BaseModel):
    solution_id: str
    steps: list[StepAnnotation]


class AnnotatedSolutions(BaseModel):
    solutions: list[SolutionAnnotation]


class StudentProfile(BaseModel):
    student_id: str
    explicit_mastered: set[str] = Field(default_factory=set)
    explicit_not_mastered: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def no_conflict(self):
        overlap = self.explicit_mastered & self.explicit_not_mastered
        if overlap:
            raise ValueError(f"Conflicting explicit states: {sorted(overlap)}")
        return self


class CheckReason(BaseModel):
    step_id: str
    concept: str
    code: Literal["EXPLICIT_NOT_MASTERED", "INFERRED_MASTERED", "UNKNOWN", "UNMAPPED", "AMBIGUOUS", "INVALID_NODE", "NO_DEPENDENCIES"]
    node_ids: list[str] = Field(default_factory=list)
    evidence: str = ""
    inference_path: list[str] = Field(default_factory=list)


class SolutionCheck(BaseModel):
    solution_id: str
    level: Literal["L1", "L2", "L3", "L4"]
    reasons: list[CheckReason]
    step_levels: dict[str, str]


class Selection(BaseModel):
    status: Literal["FEASIBLE", "NO_RELIABLE_SOLUTION"]
    selected_solution_ids: list[str]
    basis: str


class Question(BaseModel):
    question_id: str
    text: str
    source: str
    source_row: int | None = None


class ModelConfig(BaseModel):
    model: str = "mock"
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0
    max_tokens: int = 3000


class ExperimentCase(BaseModel):
    question: Question
    profile: StudentProfile


class LLMTrace(BaseModel):
    task: str
    generation_config: ModelConfig
    prompt: list[dict[str, str]]
    raw_response: str
    parsed: dict
