from __future__ import annotations

import json
from .models import ModelConfig


MOCK_QUESTION_BANK = [
    ("Q01", r"求极限 $\lim_{x\to0}\sin x/x$。"),
    ("Q02", r"求极限 $\lim_{x\to0}(1-\cos x)/x^2$。"),
    ("Q03", r"求极限 $\lim_{x\to0}(e^x-1)/x$。"),
    ("Q04", r"求极限 $\lim_{x\to0}\ln(1+x)/x$。"),
    ("Q05", r"求极限 $\lim_{x\to0}(\sin x-x)/x^3$。"),
    ("Q06", r"求极限 $\lim_{x\to0}(\tan x-x)/x^3$。"),
    ("Q07", r"求极限 $\lim_{x\to0}(1-\cos x)/(\sin x)^2$。"),
    ("Q08", r"求极限 $\lim_{x\to0}(e^{2x}-1)/\sin x$。"),
    ("Q09", r"求极限 $\lim_{x\to0}(\sqrt{1+x}-1)/x$。"),
    ("Q10", r"求极限 $\lim_{x\to0}(1+x)^{1/x}$。"),
    ("Q11", r"求极限 $\lim_{x\to0}x\sin(1/x)$。"),
    ("Q12", r"讨论 $f(x)=|x|/x$ 在 $x=0$ 处的左右极限。"),
]

SOURCE_QUESTION_IDS = [f"T{i:03d}" for i in range(99, 111)]


MOCK = {
    "Q01": {
        "generator": {"solutions": [
            {"solution_id": "S1", "name": "重要极限", "steps": [{"step_id": "S1-1", "content": "直接使用重要极限 lim(x→0) sin(x)/x = 1。"}], "final_result": "1"},
            {"solution_id": "S2", "name": "洛必达法则", "steps": [{"step_id": "S2-1", "content": "分子分母均趋于 0，应用洛必达法则得到 lim(x→0) cos(x)/1。"}, {"step_id": "S2-2", "content": "cos(x) 在 0 处连续，所以极限为 cos(0)=1。"}], "final_result": "1"},
        ]},
        "annotator": {"solutions": [
            {"solution_id": "S1", "steps": [{"step_id": "S1-1", "content": "直接使用重要极限 lim(x→0) sin(x)/x = 1。", "knowledge": [{"concept": "重要极限", "status": "MATCHED", "node_ids": ["N023"], "evidence": "直接引用 sin(x)/x 的极限公式", "unmapped_candidate": None}]}]},
            {"solution_id": "S2", "steps": [{"step_id": "S2-1", "content": "分子分母均趋于 0，应用洛必达法则得到 lim(x→0) cos(x)/1。", "knowledge": [{"concept": "洛必达法则", "status": "AMBIGUOUS", "node_ids": ["N024", "N053"], "evidence": "0/0 型极限求导", "unmapped_candidate": None}, {"concept": "基本导数公式", "status": "MATCHED", "node_ids": ["N045"], "evidence": "sin(x) 求导得到 cos(x)", "unmapped_candidate": None}]}, {"step_id": "S2-2", "content": "cos(x) 在 0 处连续，所以极限为 cos(0)=1。", "knowledge": [{"concept": "函数连续性", "status": "MATCHED", "node_ids": ["N025"], "evidence": "连续函数可代入极限", "unmapped_candidate": None}]}]},
        ]},
        "baseline_a": {"methods": ["重要极限", "洛必达法则"], "reason": "模拟模型直接建议；未经人工正确性审查"},
        "baseline_b": {"selected_solution_ids": ["S1", "S2"], "reason": "模拟模型判定；未经人工正确性审查"},
    },
    "Q02": {
        "generator": {"solutions": [
            {"solution_id": "S1", "name": "三角恒等变形", "steps": [{"step_id": "S1-1", "content": "用 1-cos(x)=2sin²(x/2)，原式化为 (1/2)[sin(x/2)/(x/2)]²。"}, {"step_id": "S1-2", "content": "由重要极限 sin(t)/t→1 得到 1/2。"}], "final_result": "1/2"},
            {"solution_id": "S2", "name": "泰勒展开", "steps": [{"step_id": "S2-1", "content": "cos(x)=1-x²/2+o(x²)，代入后得到 (x²/2+o(x²))/x²。"}, {"step_id": "S2-2", "content": "令 x→0，极限为 1/2。"}], "final_result": "1/2"},
        ]},
        "annotator": {"solutions": [
            {"solution_id": "S1", "steps": [{"step_id": "S1-1", "content": "用 1-cos(x)=2sin²(x/2)，原式化为 (1/2)[sin(x/2)/(x/2)]²。", "knowledge": [{"concept": "半角恒等式", "status": "UNMAPPED", "node_ids": [], "evidence": "使用 1-cos(x)=2sin²(x/2)", "unmapped_candidate": "三角恒等式：半角公式"}]}, {"step_id": "S1-2", "content": "由重要极限 sin(t)/t→1 得到 1/2。", "knowledge": [{"concept": "重要极限", "status": "MATCHED", "node_ids": ["N023"], "evidence": "使用 sin(t)/t→1", "unmapped_candidate": None}]}]},
            {"solution_id": "S2", "steps": [{"step_id": "S2-1", "content": "cos(x)=1-x²/2+o(x²)，代入后得到 (x²/2+o(x²))/x²。", "knowledge": [{"concept": "泰勒展开", "status": "MATCHED", "node_ids": ["N035"], "evidence": "cos(x) 的二阶展开", "unmapped_candidate": None}]}, {"step_id": "S2-2", "content": "令 x→0，极限为 1/2。", "knowledge": [{"concept": "极限计算", "status": "MATCHED", "node_ids": ["N022"], "evidence": "使用极限四则运算与 o(x²)/x²→0", "unmapped_candidate": None}]}]},
        ]},
        "baseline_a": {"methods": ["三角恒等变形", "泰勒展开"], "reason": "模拟模型直接建议"},
        "baseline_b": {"selected_solution_ids": ["S1", "S2"], "reason": "模拟模型判定"},
    },
    "Q03": {
        "generator": {"solutions": [
            {"solution_id": "S1", "name": "重要极限", "steps": [{"step_id": "S1-1", "content": "直接使用指数函数重要极限 lim(x→0)(e^x-1)/x=1。"}], "final_result": "1"},
            {"solution_id": "S2", "name": "洛必达法则", "steps": [{"step_id": "S2-1", "content": "原式为 0/0 型，洛必达法则给出 lim(x→0)e^x/1。"}, {"step_id": "S2-2", "content": "由指数函数连续性，结果是 1。"}], "final_result": "1"},
        ]},
        "annotator": {"solutions": [
            {"solution_id": "S1", "steps": [{"step_id": "S1-1", "content": "直接使用指数函数重要极限 lim(x→0)(e^x-1)/x=1。", "knowledge": [{"concept": "重要极限", "status": "MATCHED", "node_ids": ["N023"], "evidence": "直接引用指数型极限", "unmapped_candidate": None}]}]},
            {"solution_id": "S2", "steps": [{"step_id": "S2-1", "content": "原式为 0/0 型，洛必达法则给出 lim(x→0)e^x/1。", "knowledge": [{"concept": "洛必达法则", "status": "AMBIGUOUS", "node_ids": ["N024", "N053"], "evidence": "使用 0/0 型洛必达", "unmapped_candidate": None}, {"concept": "基本导数公式", "status": "MATCHED", "node_ids": ["N045"], "evidence": "e^x 的导数为 e^x", "unmapped_candidate": None}]}, {"step_id": "S2-2", "content": "由指数函数连续性，结果是 1。", "knowledge": [{"concept": "函数连续性", "status": "MATCHED", "node_ids": ["N025"], "evidence": "e^x 在 0 连续", "unmapped_candidate": None}]}]},
        ]},
        "baseline_a": {"methods": ["重要极限", "洛必达法则"], "reason": "模拟模型直接建议"},
        "baseline_b": {"selected_solution_ids": ["S1", "S2"], "reason": "模拟模型判定"},
    },
}


class MockClient:
    def __init__(self):
        self.config = ModelConfig(model="mock-scripted-v1")

    def complete(self, task: str, messages: list[dict[str, str]], case_id: str) -> str:
        if case_id not in MOCK:
            raise ValueError(f"No scripted response for {case_id}")
        return json.dumps(MOCK[case_id][task], ensure_ascii=False)
