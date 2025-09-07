from __future__ import annotations

def parse_duration_to_minutes(text: str) -> int:
    """
    Parse duration into minutes.
    Accepted formats:
      "90"      -> 90
      "90m"     -> 90
      "1:30"    -> 90
      "2h"      -> 120
      "1h15"    -> 75
      "1.5h"    -> 90
    Returns 0 for blank.
    Raises ValueError for invalid non-blank inputs.
    """
    s = (text or "").strip().lower().replace(" ", "")
    if not s:
        return 0

    # H:MM
    if ":" in s:
        h, m = s.split(":", 1)
        return int(h or 0) * 60 + int(m or 0)

    # Decimal hours like "1.5h"
    if s.endswith("h"):
        num = s[:-1]
        if "." in num:
            return int(round(float(num) * 60))
        return int(num) * 60

    # "1h15"
    if "h" in s:
        h, m = s.split("h", 1)
        return int(h or 0) * 60 + int(m or 0)

    # "90m"
    if s.endswith("m"):
        return int(s[:-1] or "0")

    # Plain minutes "90"
    return int(s)