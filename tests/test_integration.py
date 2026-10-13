import unittest
from pathlib import Path

from eduagent.cli import default_cases
from eduagent.graph import KnowledgeGraph, normalize_id
from eduagent.mock import MockClient, SOURCE_QUESTION_IDS
from eduagent.pipeline import run_case


EXCEL = Path(__file__).resolve().parents[1] / "教材知识图谱高数D.xlsx"


class WorkbookIntegrationTests(unittest.TestCase):
    def test_real_workbook_audit_and_selection(self):
        g = KnowledgeGraph.from_excel(EXCEL)
        audit = g.audit()
        self.assertEqual(audit["counts"]["nodes"], 113)
        self.assertEqual(audit["counts"]["relations_nonblank"], 143)
        self.assertEqual(audit["counts"]["questions"], 345)
        self.assertEqual(audit["counts"]["confirmed_prerequisites"], 0)
        self.assertEqual(audit["duplicate_names_not_merged"]["洛必达法则"], ["N024", "N053"])
        self.assertTrue(set(SOURCE_QUESTION_IDS) <= {q["id"] for q in g.questions})
        self.assertEqual(normalize_id("NO50"), "N050")
        results = [run_case(c, g, MockClient()) for c in default_cases()]
        self.assertEqual([r["selection"]["selected_solution_ids"] for r in results], [["S1"], [], ["S1"]])
        self.assertTrue(all(len(r["traces"]) == 4 for r in results))
        self.assertEqual({x["code"] for x in results[0]["checks"][1]["reasons"]}, {"AMBIGUOUS", "EXPLICIT_NOT_MASTERED", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
