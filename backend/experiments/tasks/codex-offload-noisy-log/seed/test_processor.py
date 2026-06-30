import unittest

from processor import classify_event


class ProcessorTests(unittest.TestCase):
    def test_alert_7732_is_critical_at_severity_7(self):
        self.assertEqual(
            classify_event({"code": "ALERT-7732", "severity": 7}),
            "critical",
        )

    def test_warn_codes_remain_warning(self):
        self.assertEqual(
            classify_event({"code": "WARN-2001", "severity": 2}),
            "warning",
        )

    def test_low_severity_unknown_stays_normal(self):
        self.assertEqual(
            classify_event({"code": "INFO-1000", "severity": 1}),
            "normal",
        )


if __name__ == "__main__":
    unittest.main()
