import unittest

from ai_engine import (
    build_free_result,
    build_pro_prompt,
    detect_risk_markers,
    prioritize_analysis,
)


class AnalysisFlowTests(unittest.TestCase):
    def test_free_is_derived_from_full_analysis(self):
        full = {
            "score": 8,
            "risks": [
                {"title": "Денежный риск"},
                {"title": "Подсудность"},
            ],
        }
        free = build_free_result(full)
        self.assertEqual(free, {"score": 8, "risk_title": "Денежный риск"})
        self.assertNotIn("total_risks", free)

    def test_fragment_prompt_forbids_missing_section_risks(self):
        prompt = build_pro_prompt("Штраф составляет 50%.", "Заказчик")
        self.assertIn("Передан фрагмент договора", prompt)
        self.assertIn("Не считай риском отсутствие разделов", prompt)

    def test_payment_fragment_markers_are_detected(self):
        text = (
            "15% от суммы, полученной Заказчиком. "
            "Очередность погашения определяется Исполнителем самостоятельно."
        )
        markers = detect_risk_markers(text)
        self.assertIn("полученн", markers)
        self.assertIn("самостоятельн", markers)

    def test_financial_risk_is_ranked_above_jurisdiction(self):
        data = {
            "score": 5,
            "risks": [
                {"title": "Не указана подсудность", "desc": "Нет суда"},
                {"title": "Неясная сумма вознаграждения", "desc": "Риск оплаты и удержаний"},
            ],
        }
        result = prioritize_analysis(data, "15% от суммы, полученной Заказчиком")
        self.assertEqual(result["risks"][0]["title"], "Неясная сумма вознаграждения")
        self.assertGreater(result["score"], 5)


if __name__ == "__main__":
    unittest.main()
