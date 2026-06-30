"""Tiny event classifier with one seeded bug."""


def classify_event(event: dict) -> str:
    code = event.get("code", "")
    severity = int(event.get("severity", 0))
    if code.startswith("ALERT-") and severity >= 9:
        return "critical"
    if code.startswith("WARN-") or severity >= 5:
        return "warning"
    return "normal"
