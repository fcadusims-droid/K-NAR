"""Testes do QA acústico — stdlib puro (EDL + estatísticas de mix)."""

import unittest

from k_nar.qa import check_mix, check_timeline, format_report
from k_nar.timeline import Placement, Timeline, TimingPolicy


def _tl(placements):
    return Timeline(scene_id="c", ambiance="seco", placements=placements)


class TestTimelineQA(unittest.TestCase):
    def test_clean_timeline_no_issues(self):
        tl = _tl([
            Placement("a", "A", start_ms=0, duration_ms=1000, pan=0, text="oi",
                      entry_type="sequencial"),
            Placement("b", "B", start_ms=1200, duration_ms=1000, pan=0, text="ola",
                      entry_type="sequencial"),
        ])
        self.assertEqual(check_timeline(tl, TimingPolicy()), [])

    def test_flags_unexpected_sequential_crossing(self):
        # B é sequencial mas começa antes de A terminar -> erro
        tl = _tl([
            Placement("a", "A", start_ms=0, duration_ms=1000, pan=0, text="oi",
                      entry_type="sequencial"),
            Placement("b", "B", start_ms=500, duration_ms=1000, pan=0, text="ola",
                      entry_type="sequencial"),
        ])
        issues = check_timeline(tl, TimingPolicy())
        self.assertTrue(any(i.code == "cruzamento_inesperado" for i in issues))
        self.assertEqual(issues[0].severity, "error")

    def test_flags_swallowed_overlap(self):
        # B (curta) entra em sobreposição e é quase toda coberta por A (longa)
        tl = _tl([
            Placement("a", "A", start_ms=0, duration_ms=3000, pan=0, text="fala longa",
                      entry_type="sequencial"),
            Placement("b", "B", start_ms=100, duration_ms=400, pan=0, text="curta",
                      entry_type="sobreposicao"),
        ])
        issues = check_timeline(tl, TimingPolicy())
        self.assertTrue(any(i.code == "fala_engolida" for i in issues))

    def test_intended_overlap_not_swallowed_is_clean(self):
        # sobreposição parcial (só o começo) não engole
        tl = _tl([
            Placement("a", "A", start_ms=0, duration_ms=2000, pan=0, text="a",
                      entry_type="sequencial"),
            Placement("b", "B", start_ms=1800, duration_ms=2000, pan=0, text="b",
                      entry_type="sobreposicao"),
        ])
        codes = {i.code for i in check_timeline(tl, TimingPolicy())}
        self.assertNotIn("fala_engolida", codes)

    def test_flags_over_aggressive_cut(self):
        # corte deixa só 100ms audíveis, abaixo do mínimo (400ms)
        p = Placement("a", "A", start_ms=0, duration_ms=2000, pan=0, text="a",
                      entry_type="sequencial", hard_cut_ms=100)
        tl = _tl([p, Placement("b", "B", start_ms=100, duration_ms=1000, pan=0,
                               text="b", entry_type="interrupcao")])
        issues = check_timeline(tl, TimingPolicy())
        self.assertTrue(any(i.code == "corte_agressivo" for i in issues))


class TestMixQA(unittest.TestCase):
    def test_clipping_is_error(self):
        issues = check_mix({"peak": 1.0, "clipped_samples": 12, "clipped_ratio": 0.001})
        self.assertTrue(any(i.code == "clipping" and i.severity == "error" for i in issues))

    def test_high_peak_is_warn(self):
        issues = check_mix({"peak": 0.99, "clipped_samples": 0, "clipped_ratio": 0.0})
        self.assertEqual(issues[0].code, "pico_alto")
        self.assertEqual(issues[0].severity, "warn")

    def test_healthy_mix_clean(self):
        self.assertEqual(check_mix({"peak": 0.9, "clipped_samples": 0, "clipped_ratio": 0.0}), [])


class TestReport(unittest.TestCase):
    def test_empty_report(self):
        self.assertIn("nenhum problema", format_report([]))

    def test_report_lists_issues(self):
        tl = _tl([
            Placement("a", "A", start_ms=0, duration_ms=1000, pan=0, text="a",
                      entry_type="sequencial"),
            Placement("b", "B", start_ms=500, duration_ms=1000, pan=0, text="b",
                      entry_type="sequencial"),
        ])
        report = format_report(check_timeline(tl, TimingPolicy()))
        self.assertIn("cruzamento_inesperado", report)


if __name__ == "__main__":
    unittest.main()
