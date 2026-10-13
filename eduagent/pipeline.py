from __future__ import annotations

import json
import os
from collections import deque
from typing import Protocol
import httpx

from .graph import KnowledgeGraph
from .models import (AnnotatedSolutions, BaselineAResult, BaselineBResult, CheckReason, ExperimentCase, GeneratedSolutions,
                     KnowledgeUse, LLMTrace, MatchStatus, ModelConfig, Selection,
                     SolutionCheck, StudentProfile)


class ModelClient(Protocol):
    config: ModelConfig
    def complete(self, task: str, messages: list[dict[str, str]], case_id: str) -> str: ...


class OpenAICompatibleClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for live runs")

    def complete(self, task: str, messages: list[dict[str, str]], case_id: str) -> str:
        response = httpx.post(
            self.config.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.config.model, "messages": messages,
                  "temperature": self.config.temperature, "max_tokens": self.config.max_tokens,
                  "response_format": {"type": "json_object"}}, timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def call_json(client: ModelClient, task: str, messages: list[dict[str, str]], case_id: str, schema):
    raw = client.complete(task, messages, case_id)
    parsed = schema.model_validate_json(raw)
    trace = LLMTrace(task=task, generation_config=client.config, prompt=messages,
                     raw_response=raw, parsed=parsed.model_dump(mode="json"))
    return parsed, trace


def generate(client: ModelClient, case: ExperimentCase):
    messages = [
        {"role": "system", "content": "You are a mathematics solver. Return JSON only: {solutions:[{solution_id,name,steps:[{step_id,content}],final_result}]}. Generate up to 3 genuinely different complete derivations. Do not assume they are correct. Do not use a student profile."},
        {"role": "user", "content": case.question.text},
    ]
    return call_json(client, "generator", messages, case.question.question_id, GeneratedSolutions)


def annotate(client: ModelClient, case: ExperimentCase, generated: GeneratedSolutions, graph: KnowledgeGraph):
    all_steps = "\n".join(s.content for sol in generated.solutions for s in sol.steps)
    candidates = [n.model_dump() for n in graph.retrieve(case.question.text + "\n" + all_steps)]
    messages = [
        {"role": "system", "content": "Independently identify every directly used mathematical concept in EACH step. Return JSON {solutions:[{solution_id,steps:[{step_id,content,knowledge:[{concept,status,node_ids,evidence,unmapped_candidate}]}]}]}. status is MATCHED, UNMAPPED, or AMBIGUOUS. A MATCHED item has one graph node ID, AMBIGUOUS has at least two, UNMAPPED has none. Include implicit dependencies where necessary. Candidate nodes are hints, not an exhaustive ontology. Do not force a match. Do not decide feasibility."},
        {"role": "user", "content": json.dumps({"question": case.question.model_dump(), "solutions": generated.model_dump(), "retrieved_candidates": candidates}, ensure_ascii=False)},
    ]
    parsed, trace = call_json(client, "annotator", messages, case.question.question_id, AnnotatedSolutions)
    expected = {(sol.solution_id, step.step_id): step.content for sol in generated.solutions for step in sol.steps}
    seen = set()
    for sol in parsed.solutions:
        for step in sol.steps:
            key = (sol.solution_id, step.step_id)
            if key not in expected or key in seen or step.content != expected[key]:
                raise ValueError(f"Annotation step mismatch: {key}")
            seen.add(key)
            for use in step.knowledge:
                invalid = [nid for nid in use.node_ids if nid not in graph.nodes]
                if invalid:
                    use.status = MatchStatus.UNMAPPED
                    use.unmapped_candidate = use.unmapped_candidate or f"Invalid graph IDs: {', '.join(invalid)}"
                    use.node_ids = []
    if seen != set(expected) or {s.solution_id for s in parsed.solutions} != {s.solution_id for s in generated.solutions}:
        raise ValueError("Annotation must cover exactly every generated step and solution")
    return parsed, trace


def infer_mastery(profile: StudentProfile, graph: KnowledgeGraph) -> dict[str, list[str]]:
    inferred: dict[str, list[str]] = {}
    for mastered in sorted(profile.explicit_mastered):
        if mastered not in graph.confirmed:
            continue
        queue = deque([(mastered, [mastered])])
        visited = {mastered}
        while queue:
            current, path = queue.popleft()
            for prerequisite in graph.confirmed.successors(current):
                if prerequisite in visited or prerequisite in profile.explicit_not_mastered:
                    continue
                visited.add(prerequisite)
                next_path = path + [prerequisite]
                if prerequisite not in profile.explicit_mastered and (prerequisite not in inferred or len(next_path) < len(inferred[prerequisite])):
                    inferred[prerequisite] = next_path
                queue.append((prerequisite, next_path))
    return inferred


def check(annotations: AnnotatedSolutions, profile: StudentProfile, graph: KnowledgeGraph, mode: str = "strict") -> tuple[list[SolutionCheck], dict[str, list[str]]]:
    if mode not in {"strict", "inference"}:
        raise ValueError("mode must be strict or inference")
    inferred = infer_mastery(profile, graph) if mode == "inference" else {}
    checks = []
    for sol in annotations.solutions:
        reasons: list[CheckReason] = []
        step_levels = {}
        for step in sol.steps:
            step_reasons: list[CheckReason] = []
            if not step.knowledge:
                step_reasons.append(CheckReason(step_id=step.step_id, concept="unspecified", code="NO_DEPENDENCIES", evidence="Annotator provided no dependencies; manual review required"))
            for use in step.knowledge:
                base = {"step_id": step.step_id, "concept": use.concept, "node_ids": use.node_ids, "evidence": use.evidence}
                if use.status != MatchStatus.MATCHED:
                    step_reasons.append(CheckReason(**base, code=use.status.value))
                else:
                    nid = use.node_ids[0]
                    if nid not in graph.nodes:
                        step_reasons.append(CheckReason(**base, code="INVALID_NODE"))
                    elif nid in profile.explicit_not_mastered:
                        step_reasons.append(CheckReason(**base, code="EXPLICIT_NOT_MASTERED"))
                    elif nid in profile.explicit_mastered:
                        pass
                    elif nid in inferred:
                        step_reasons.append(CheckReason(**base, code="INFERRED_MASTERED", inference_path=inferred[nid]))
                    else:
                        step_reasons.append(CheckReason(**base, code="UNKNOWN"))
            codes = {r.code for r in step_reasons}
            step_levels[step.step_id] = "L4" if "EXPLICIT_NOT_MASTERED" in codes else "L3" if codes & {"UNKNOWN", "UNMAPPED", "AMBIGUOUS", "INVALID_NODE", "NO_DEPENDENCIES"} else "L2" if "INFERRED_MASTERED" in codes else "L1"
            reasons.extend(step_reasons)
        levels = set(step_levels.values())
        level = "L4" if "L4" in levels else "L3" if "L3" in levels else "L2" if "L2" in levels else "L1"
        checks.append(SolutionCheck(solution_id=sol.solution_id, level=level, reasons=reasons, step_levels=step_levels))
    return checks, inferred


def select(checks: list[SolutionCheck]) -> Selection:
    for level in ("L1", "L2"):
        ids = [c.solution_id for c in checks if c.level == level]
        if ids:
            return Selection(status="FEASIBLE", selected_solution_ids=ids,
                             basis="All explicitly mastered" if level == "L1" else "Includes graph-inferred mastery; not test-confirmed")
    return Selection(status="NO_RELIABLE_SOLUTION", selected_solution_ids=[], basis="No L1/L2 solution; review diagnostics")


def run_case(case: ExperimentCase, graph: KnowledgeGraph, client: ModelClient, mode: str = "strict", baselines: bool = True) -> dict:
    unknown_ids = (case.profile.explicit_mastered | case.profile.explicit_not_mastered) - graph.nodes.keys()
    if unknown_ids:
        raise ValueError(f"Profile contains unknown IDs: {sorted(unknown_ids)}")
    generated, gen_trace = generate(client, case)
    annotated, ann_trace = annotate(client, case, generated, graph)
    checks, inferred = check(annotated, case.profile, graph, mode)
    selection = select(checks)
    traces = [gen_trace, ann_trace]
    baseline_results = {}
    if baselines:
        a_messages = [
            {"role": "system", "content": "Baseline A: using only the problem and student profile, propose available solution methods. Return JSON {methods:[string],reason:string}. No graph is provided."},
            {"role": "user", "content": json.dumps({"question": case.question.model_dump(), "profile": case.profile.model_dump(mode="json")}, ensure_ascii=False)},
        ]
        b_messages = [
            {"role": "system", "content": "Baseline B: inspect the complete candidate solutions and student profile, decide which solution IDs are within scope. Return JSON {selected_solution_ids:[string],reason:string}. Do not use a graph."},
            {"role": "user", "content": json.dumps({"question": case.question.model_dump(), "profile": case.profile.model_dump(mode="json"), "solutions": generated.model_dump()}, ensure_ascii=False)},
        ]
        for task, messages, schema in [("baseline_a", a_messages, BaselineAResult), ("baseline_b", b_messages, BaselineBResult)]:
            parsed, trace = call_json(client, task, messages, case.question.question_id, schema)
            if task == "baseline_b" and set(parsed.selected_solution_ids) - {s.solution_id for s in generated.solutions}:
                raise ValueError("Baseline B selected an unknown solution ID")
            baseline_results[task] = parsed.model_dump()
            traces.append(trace)
    return {"case": case.model_dump(mode="json"), "mode": mode,
            "model_config": client.config.model_dump(), "generated": generated.model_dump(mode="json"),
            "annotations": annotated.model_dump(mode="json"), "inferred_mastery_paths": inferred,
            "checks": [c.model_dump(mode="json") for c in checks], "selection": selection.model_dump(),
            "baselines": baseline_results, "traces": [t.model_dump(mode="json") for t in traces],
            "limitations": ["Mathematical correctness has not been verified", "Missing knowledge annotations cannot be ruled out"]}
