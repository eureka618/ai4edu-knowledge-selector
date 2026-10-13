from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .graph import KnowledgeGraph
from .mock import MockClient, MOCK_QUESTION_BANK, SOURCE_QUESTION_IDS
from .models import ExperimentCase, ModelConfig, Question, StudentProfile
from .pipeline import OpenAICompatibleClient, run_case


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def default_cases():
    profiles = {
        "Q01": StudentProfile(student_id="P01", explicit_mastered={"N023"}, explicit_not_mastered={"N045"}),
        "Q02": StudentProfile(student_id="P02", explicit_mastered={"N023", "N022"}, explicit_not_mastered={"N035"}),
        "Q03": StudentProfile(student_id="P03", explicit_mastered={"N023"}, explicit_not_mastered={"N024"}),
    }
    return [ExperimentCase(question=Question(question_id=qid, text=text, source="PROJECT_AUTHORED_NOT_EXCEL"), profile=profiles[qid]) for qid,text in MOCK_QUESTION_BANK if qid in profiles]


def audit_markdown(audit: dict) -> str:
    c = audit["counts"]
    return "\n".join([
        "# 教材知识图谱高数D：数据审计",
        "",
        "来源：项目目录中的原始 Excel；本程序只读，不修改工作簿。详细逐行证据见 `audit.json`。",
        "",
        f"- 知识点：{c['nodes']}；非空知识点关系：{c['relations_nonblank']}；题目：{c['questions']}；题目关联：{c['question_links']}。",
        f"- 章节：{c['chapters']}；章节关联：{c['chapter_links']}；已确认必要前置边：{c['confirmed_prerequisites']}。",
        f"- 格式不一致的知识点 ID：{len(audit['raw_id_irregularities'])}；同名节点组：{len(audit['duplicate_names_not_merged'])}。",
        f"- 无效知识点关系：{len(audit['invalid_knowledge_relations'])}；无效题目关联：{len(audit['invalid_question_links'])}；无效章节关联：{len(audit['invalid_chapter_links'])}。",
        f"- 待人工核对的关系描述/端点不一致线索：{len(audit['possible_semantic_conflicts'])}。该启发式仅产生审查候选，不断言每条都错。",
        f"- 题目文字含 `\\lim` 或“极限”的原题共 {len(audit['limit_question_ids_by_text'])} 道，但包含导数和级数题，不能直接当作本章题目数。",
        "- 本项目选取原表 T099–T110 共 12 道连续极限例题作为待实验题集；另有 3 道自编题仅供离线流程验证。",
        "",
        "## 审计结论",
        "",
        "原表的关系标签和描述不足以证明必要前置关系。尤其开头若干关系描述提到的概念与端点节点名称不对应。默认全部不参与掌握推断；只有独立人工审查后，通过带行号、方向、`necessity=necessary` 和 reviewer 的 JSON 才可确认。",
        "",
        "ID 规范化只处理形如 `NO50` 到 `N050` 的机械格式差异；同名概念保留为独立节点。题目与知识点的现有链接不作为解法逐步依赖的真值。",
        "",
        "## 关系类型统计",
        "",
        *[f"- {k or '(空)'}：{v}" for k,v in sorted(audit['relation_types'].items())],
        "",
    ])


def main():
    p = argparse.ArgumentParser(description="Knowledge-constrained mathematics solution research pipeline")
    p.add_argument("command", choices=["audit", "mock", "run"])
    p.add_argument("--excel", default="教材知识图谱高数D.xlsx")
    p.add_argument("--out", default="outputs")
    p.add_argument("--approvals", help="JSON list of manually confirmed necessary prerequisite edges")
    p.add_argument("--mode", choices=["strict", "inference"], default="strict")
    p.add_argument("--cases", help="JSON list of ExperimentCase objects; required for live run")
    p.add_argument("--model", default="")
    p.add_argument("--base-url", default="https://api.openai.com/v1")
    p.add_argument("--temperature", type=float, default=0)
    p.add_argument("--max-tokens", type=int, default=3000)
    args = p.parse_args()
    graph = KnowledgeGraph.from_excel(args.excel)
    out = Path(args.out)
    if args.approvals:
        errors = graph.confirm_prerequisites(json.loads(Path(args.approvals).read_text(encoding="utf-8")))
        if errors:
            raise ValueError("Invalid approvals: " + "; ".join(errors))
    audit = graph.audit()
    audit["source_workbook"] = {"path": str(Path(args.excel).resolve()), "sha256": hashlib.sha256(Path(args.excel).read_bytes()).hexdigest()}
    write_json(out / "audit.json", audit)
    (out / "audit.md").write_text(audit_markdown(audit), encoding="utf-8")
    write_json(out / "graph.json", {"nodes": [n.model_dump() for n in graph.nodes.values()], "relations": [r.model_dump() for r in graph.relations], "confirmed_edges": [{"advanced_id": a, "prerequisite_id": b, **data} for a,b,data in graph.confirmed.edges(data=True)]})
    source_questions = {q["id"]: q for q in graph.questions}
    selected = [source_questions[qid] for qid in SOURCE_QUESTION_IDS]
    write_json(out / "question_bank.json", [{"question_id": q["id"], "text": q["text"], "source": "EXCEL_题目节点", "source_row": q["source_row"], "answer_reference": q["answer"]} for q in selected])
    profile_patterns = [({"N022"}, {"N024", "N035"}), ({"N022", "N023"}, {"N035"}), ({"N022", "N024"}, {"N035"}), ({"N022", "N035"}, {"N024"})]
    source_cases = []
    for i,q in enumerate(selected):
        mastered, not_mastered = profile_patterns[i % len(profile_patterns)]
        source_cases.append(ExperimentCase(question=Question(question_id=q["id"], text=q["text"], source="EXCEL_题目节点", source_row=q["source_row"]), profile=StudentProfile(student_id=f"SCENARIO_{q['id']}", explicit_mastered=mastered, explicit_not_mastered=not_mastered)).model_dump(mode="json"))
    write_json(out / "source_experiment_cases.review.json", source_cases)
    if args.command == "audit":
        print(json.dumps(audit["counts"], ensure_ascii=False))
        return
    if args.command == "mock":
        cases = default_cases()
        client = MockClient()
    else:
        if not args.cases or not args.model:
            p.error("run requires --cases and --model")
        cases = [ExperimentCase.model_validate(x) for x in json.loads(Path(args.cases).read_text(encoding="utf-8"))]
        client = OpenAICompatibleClient(ModelConfig(model=args.model, base_url=args.base_url, temperature=args.temperature, max_tokens=args.max_tokens))
    summary = []
    for case in cases:
        result = run_case(case, graph, client, args.mode)
        write_json(out / "cases" / f"{case.question.question_id}.json", result)
        summary.append({"case_id": case.question.question_id, "source": case.question.source, "mode": args.mode, "levels": {x["solution_id"]: x["level"] for x in result["checks"]}, "selected": result["selection"]["selected_solution_ids"], "baseline_a": result["baselines"].get("baseline_a"), "baseline_b": result["baselines"].get("baseline_b"), "review_status": "NOT_HUMAN_ADJUDICATED"})
    write_json(out / "human_review_template.json", [{"case_id": row["case_id"], "solution_id": sid, "system_level": level, "solution_mathematically_correct": None, "all_direct_dependencies_identified": None, "dependency_mapping_correct": None, "actually_within_student_scope": None, "reviewer": None, "notes": ""} for row in summary for sid,level in row["levels"].items()])
    write_json(out / "comparison.json", {"config": {"model": client.config.model_dump(), "mode": args.mode, "case_count": len(cases), "approved_edge_count": graph.confirmed.number_of_edges()}, "results": summary, "metrics": None, "metrics_reason": "No human-reviewed ground truth; model judgments are not accuracy labels"})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
