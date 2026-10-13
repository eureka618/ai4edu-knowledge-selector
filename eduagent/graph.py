from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
import networkx as nx
import openpyxl
from pydantic import BaseModel, Field


def normalize_id(value: object) -> str:
    raw = str(value or "").strip().upper()
    match = re.fullmatch(r"N[O0]*(\d+)", raw)
    if match:
        return f"N{int(match.group(1)):03d}"
    return raw


class Node(BaseModel):
    id: str
    raw_id: str
    name: str
    description: str = ""
    kind: str = ""
    source_sheet: str
    source_row: int
    aliases: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    start_id: str
    end_id: str
    raw_start_id: str
    raw_end_id: str
    relation: str
    description: str = ""
    source_sheet: str
    source_row: int
    audit_status: str = "UNCONFIRMED"


class KnowledgeGraph:
    def __init__(self, nodes: list[Node], relations: list[Relation], questions: list[dict], question_links: list[dict], chapters: list[dict], chapter_links: list[dict]):
        self.raw_nodes = nodes
        self.nodes = {n.id: n for n in nodes}
        self.relations = relations
        self.questions = questions
        self.question_links = question_links
        self.chapters = chapters
        self.chapter_links = chapter_links
        self.confirmed = nx.DiGraph()
        self.confirmed.add_nodes_from(self.nodes)
        self.alias_index: dict[str, set[str]] = defaultdict(set)
        for n in nodes:
            for alias in [n.id, n.raw_id, n.name, *n.aliases]:
                self.alias_index[alias.casefold()].add(n.id)

    @classmethod
    def from_excel(cls, path: str | Path) -> "KnowledgeGraph":
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        def records(sheet, columns):
            for rowno, row in enumerate(wb[sheet].iter_rows(min_row=2, values_only=True), 2):
                if not any(row[:columns]):
                    continue
                yield rowno, ["" if x is None else str(x).strip() for x in row[:columns]]
        nodes = [Node(id=normalize_id(v[0]), raw_id=v[0], name=v[1], kind=v[2], description=v[3], source_sheet="知识点节点", source_row=r) for r,v in records("知识点节点",4)]
        rels = [Relation(start_id=normalize_id(v[0]), end_id=normalize_id(v[2]), raw_start_id=v[0], raw_end_id=v[2], relation=v[1], description=v[3], source_sheet="知识点关系", source_row=r) for r,v in records("知识点关系",4)]
        questions = [dict(id=v[0], text=v[1], answer=v[2], description=v[3], grade=v[4], knowledge=v[5], source_sheet="题目节点", source_row=r) for r,v in records("题目节点",6)]
        qlinks = [dict(question_id=v[0], relation=v[1], node_id=normalize_id(v[2]), source_row=r) for r,v in records("题目与知识点关系",3)]
        chapters = [dict(id=v[0], name=v[1], description=v[2], source_row=r) for r,v in records("章节节点",3)]
        clinks = [dict(chapter_id=v[0], relation=v[1], node_id=normalize_id(v[2]), source_row=r) for r,v in records("章节与知识点关系",3)]
        wb.close()
        graph = cls(nodes, rels, questions, qlinks, chapters, clinks)
        for rel in graph.relations:
            if rel.start_id not in graph.nodes or rel.end_id not in graph.nodes:
                rel.audit_status = "INVALID_REFERENCE"
            elif rel.start_id == rel.end_id:
                rel.audit_status = "SELF_REFERENCE"
            elif rel.relation not in {"前提", "依赖", "基础", "基于"}:
                rel.audit_status = "NON_PREREQUISITE_OR_UNCLEAR"
            else:
                rel.audit_status = "NEEDS_SEMANTIC_REVIEW"
        return graph

    def confirm_prerequisites(self, approvals: list[dict]) -> list[str]:
        """Approval specifies workbook row and direction: prerequisite -> advanced."""
        errors = []
        by_row = {r.source_row: r for r in self.relations}
        for item in approvals:
            rel = by_row.get(item.get("source_row"))
            if not rel or item.get("prerequisite_id") not in self.nodes or item.get("advanced_id") not in self.nodes:
                errors.append(f"Invalid approval: {item}")
                continue
            if {item["prerequisite_id"], item["advanced_id"]} != {rel.start_id, rel.end_id}:
                errors.append(f"Approval endpoints differ from row {rel.source_row}")
                continue
            if item.get("necessity") != "necessary" or item.get("reviewer") in (None, ""):
                errors.append(f"Missing necessity/reviewer for row {rel.source_row}")
                continue
            before, after = item["prerequisite_id"], item["advanced_id"]
            self.confirmed.add_edge(after, before, source_row=rel.source_row, reviewer=item["reviewer"])
            if not nx.is_directed_acyclic_graph(self.confirmed):
                self.confirmed.remove_edge(after, before)
                errors.append(f"Cycle rejected at row {rel.source_row}")
            else:
                rel.audit_status = "CONFIRMED_NECESSARY_PREREQUISITE"
        return errors

    def retrieve(self, text: str, limit: int = 12) -> list[Node]:
        normalized = text.casefold()
        scores = Counter()
        for n in self.nodes.values():
            for term in [n.name, *n.aliases]:
                if len(term) >= 2 and term.casefold() in normalized:
                    scores[n.id] += 5 + len(term)
            for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", n.name + " " + n.description):
                if token.casefold() in normalized:
                    scores[n.id] += 1
        return [self.nodes[k] for k,_ in scores.most_common(limit)]

    def audit(self) -> dict:
        names = defaultdict(list)
        for n in self.nodes.values():
            names[n.name].append(n.id)
        normalized_ids = Counter(n.id for n in self.raw_nodes)
        invalid = [r.model_dump() for r in self.relations if r.audit_status == "INVALID_REFERENCE"]
        semantic = []
        for r in self.relations:
            if r.start_id in self.nodes and r.end_id in self.nodes and r.description:
                a, b = self.nodes[r.start_id], self.nodes[r.end_id]
                if a.name not in r.description and b.name not in r.description:
                    semantic.append({"row": r.source_row, "start": f"{a.id}:{a.name}", "end": f"{b.id}:{b.name}", "description": r.description, "status": "POSSIBLE_MISMATCH_REVIEW_REQUIRED"})
        qids = {q["id"] for q in self.questions}
        return {
            "counts": {"nodes": len(self.nodes), "relations_nonblank": len(self.relations), "questions": len(self.questions), "question_links": len(self.question_links), "chapters": len(self.chapters), "chapter_links": len(self.chapter_links), "confirmed_prerequisites": self.confirmed.number_of_edges()},
            "raw_id_irregularities": [{"raw": n.raw_id, "normalized": n.id, "row": n.source_row} for n in self.nodes.values() if n.raw_id != n.id],
            "normalized_id_collisions": {k: v for k,v in normalized_ids.items() if v > 1},
            "duplicate_names_not_merged": {k:v for k,v in names.items() if len(v)>1},
            "invalid_knowledge_relations": invalid,
            "invalid_question_links": [x for x in self.question_links if x["question_id"] not in qids or x["node_id"] not in self.nodes],
            "invalid_chapter_links": [x for x in self.chapter_links if x["node_id"] not in self.nodes or x["chapter_id"] not in {c["id"] for c in self.chapters}],
            "relation_types": dict(Counter(r.relation for r in self.relations)),
            "relation_audit_statuses": dict(Counter(r.audit_status for r in self.relations)),
            "possible_semantic_conflicts": semantic,
            "limit_question_ids_by_text": [q["id"] for q in self.questions if "\\lim" in q["text"] or "极限" in q["text"]],
        }
