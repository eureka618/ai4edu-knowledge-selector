# AI4Edu：知识约束解法选择研究模块

本项目是 Tutor Agent 的上游研究模块。输入题目、学生显式知识状态和原始教材图谱；输出完整候选解法、逐步知识标注、确定性约束诊断及所有可靠可行解法。数学正确性与知识适配性分开处理，当前没有自动数学正确性验证。

## 项目结构与顺序

1. M1：`eduagent/graph.py` 只读导入 Excel，规范化 ID，保留原始 ID/工作表/行号，输出审计及未确认关系。`outputs/mock/audit.md` 是实际运行结果。
2. M2：`models.py` 定义 Pydantic JSON 契约；`pipeline.py` 实现 Generator → 独立 Annotator → Mastery Inference → Checker → Selector；`mock.py` 提供 3 个离线脚本案例。
3. M3：同一候选解法进入 Baseline B 与 Ours；Baseline A 只看题目和画像。`comparison.json` 保存三方案输出。`human_review_template.json` 留给人工标注，未审核前不计算准确率。

`T099`–`T110` 是从原始题目表选出的 12 道极限题，保存在 `question_bank.json`；`source_experiment_cases.review.json` 为其预置研究情境，学生状态是待审查的实验设定，不是真实学生数据。离线 Q01–Q03 是单独标注为自编的流程验证题，不作为 Excel 原题或模型效果证据。

## 安装与运行

Python 3.10+。在项目目录执行：

```powershell
python -m pip install -r requirements.txt
python -m eduagent.cli audit --out outputs/audit
python -m eduagent.cli mock --out outputs/mock
python -m unittest discover -s tests -v
```

本机可用的预装环境为 `D:\Anaconda\python.exe`。真实 OpenAI-compatible API 调用：

```powershell
$env:OPENAI_API_KEY = "<your key>"
python -m eduagent.cli run --cases outputs/mock/source_experiment_cases.review.json --model <model-id> --base-url https://api.example.com/v1 --out outputs/live
```

`--mode inference` 启用经确认前置边的推断；默认 `strict`。生成温度、最大 token、模型名和 URL 可由 CLI 配置。API Key 仅从环境变量读取。模型服务须支持 Chat Completions 的 JSON object response format。真实运行耗费模型调用，当前环境未提供 API Key，因此仅执行 mock。

## 接口与判断规则

`ExperimentCase` 含 `Question` 和 `StudentProfile`。画像 ID 必须是规范化的 `N001` 形式。`GeneratedSolutions` 每解最多 3 种，保留完整步骤与结果；`AnnotatedSolutions` 中每步可有多个 `KnowledgeUse`，状态为 MATCHED、UNMAPPED 或 AMBIGUOUS。标注必须逐步覆盖生成内容，非法节点 ID 转为 UNMAPPED 后才进入检查，原始响应仍在 trace 中。

Candidate Retrieval 在完整图谱中按名称/描述召回，Semantic Matching 由独立 LLM 调用完成。召回不是白名单；缺失概念允许 UNMAPPED。`SolutionCheck` 包含每步等级和所有诊断原因。L4（显式未掌握）优先于 L3（未知/歧义/未映射），再到 L2（仅推断掌握）和 L1（均显式掌握）；异常原因并行保存。Selector 返回全部 L1；无 L1 才返回全部 L2；否则返回无可靠解法。

确认前置关系的文件格式见 `confirmed_prerequisites.example.json`。每条需 `source_row`、`prerequisite_id`、`advanced_id`、`necessity: "necessary"`、`reviewer`，运行时用 `--approvals path.json` 加载。方向是高级节点 → 必要前置节点；循环会拒绝。当前原表无已人工确认关系，默认推断数为零。可替代路径不得作为必要边录入。只读图谱快照及确认后的审计状态保存在 `graph.json`。

## 当前实测与局限

离线 Q01：S1=L1、S2=L4，选 S1；Q02：S1=L3、S2=L4，无可靠解；Q03：S1=L1、S2=L3，选 S1。这是脚本响应的控制流程测试，不代表 LLM 效果。三个案例的 Prompt、原始响应、结构化数据、逐步检查和 Baseline 输出均在 `outputs/mock/cases/`。

原表有 113 个知识点、143 条非空知识关系、345 道题、595 条题目关联；64 个知识点 ID 格式不统一。`N024` 与 `N053` 同名“洛必达法则”，未合并。关系描述与端点的可能冲突有 72 条启发式线索，见 `audit.json`，需人工判断。没有确认必要前置边，因此真实图谱目前不能证明推断掌握。LLM 可能漏标隐含知识点；即便 L1 也只表示已识别依赖的状态，不能保证数学推导正确。后续优先审核关系语义、歧义节点及逐步依赖，并在审核 Ground Truth 后再计算 Precision/Recall。
