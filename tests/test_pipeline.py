import unittest

from eduagent.graph import KnowledgeGraph, Node, Relation
from eduagent.models import (AnnotatedSolutions, KnowledgeUse, MatchStatus, SolutionAnnotation,
                             StepAnnotation, StudentProfile)
from eduagent.pipeline import check, infer_mastery, select


def graph():
    nodes = [Node(id=f"N{i:03d}", raw_id=f"N{i:03d}", name=str(i), source_sheet="test", source_row=i) for i in range(1, 5)]
    rels = [Relation(start_id="N001", end_id="N002", raw_start_id="N001", raw_end_id="N002", relation="前提", source_sheet="test", source_row=2),
            Relation(start_id="N002", end_id="N003", raw_start_id="N002", raw_end_id="N003", relation="前提", source_sheet="test", source_row=3)]
    return KnowledgeGraph(nodes, rels, [], [], [], [])


class PipelineTests(unittest.TestCase):
    def test_inference_requires_confirmation_and_respects_explicit_negative(self):
        g = graph()
        profile = StudentProfile(student_id="x", explicit_mastered={"N003"})
        self.assertEqual(infer_mastery(profile, g), {})
        self.assertEqual(g.confirm_prerequisites([{"source_row": 3, "prerequisite_id": "N002", "advanced_id": "N003", "necessity": "necessary", "reviewer": "human"}, {"source_row": 2, "prerequisite_id": "N001", "advanced_id": "N002", "necessity": "necessary", "reviewer": "human"}]), [])
        self.assertEqual(infer_mastery(profile, g)["N001"], ["N003", "N002", "N001"])
        negative = StudentProfile(student_id="x", explicit_mastered={"N003"}, explicit_not_mastered={"N002"})
        self.assertEqual(infer_mastery(negative, g), {})

    def test_all_diagnostics_retained_with_l4_priority(self):
        g = graph()
        a = AnnotatedSolutions(solutions=[SolutionAnnotation(solution_id="S", steps=[StepAnnotation(step_id="1", content="step", knowledge=[KnowledgeUse(concept="bad", status=MatchStatus.MATCHED, node_ids=["N001"], evidence="e"), KnowledgeUse(concept="missing", status=MatchStatus.UNMAPPED, evidence="e")])])])
        checks, _ = check(a, StudentProfile(student_id="x", explicit_not_mastered={"N001"}), g)
        self.assertEqual(checks[0].level, "L4")
        self.assertEqual({r.code for r in checks[0].reasons}, {"EXPLICIT_NOT_MASTERED", "UNMAPPED"})
        self.assertEqual(select(checks).status, "NO_RELIABLE_SOLUTION")

    def test_cycle_rejected(self):
        g = graph()
        g.relations.append(Relation(start_id="N003", end_id="N001", raw_start_id="N003", raw_end_id="N001", relation="前提", source_sheet="test", source_row=4))
        valid = [{"source_row": r, "prerequisite_id": a, "advanced_id": b, "necessity": "necessary", "reviewer": "human"} for r,a,b in [(2,"N001","N002"),(3,"N002","N003"),(4,"N003","N001")]]
        self.assertIn("Cycle rejected", g.confirm_prerequisites(valid)[0])

    def test_l2_only_after_confirmed_necessary_edge(self):
        g = graph()
        g.confirm_prerequisites([{"source_row": 3, "prerequisite_id": "N002", "advanced_id": "N003", "necessity": "necessary", "reviewer": "human"}])
        annotation = AnnotatedSolutions(solutions=[SolutionAnnotation(solution_id="S", steps=[StepAnnotation(step_id="1", content="step", knowledge=[KnowledgeUse(concept="prerequisite", status=MatchStatus.MATCHED, node_ids=["N002"], evidence="e")])])])
        profile = StudentProfile(student_id="x", explicit_mastered={"N003"})
        strict, _ = check(annotation, profile, g, "strict")
        inferred, paths = check(annotation, profile, g, "inference")
        self.assertEqual(strict[0].level, "L3")
        self.assertEqual(inferred[0].level, "L2")
        self.assertEqual(paths["N002"], ["N003", "N002"])
        self.assertEqual(select(inferred).selected_solution_ids, ["S"])


if __name__ == "__main__":
    unittest.main()
