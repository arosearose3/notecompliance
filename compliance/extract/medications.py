"""Parse the Medications section of a clinical note."""

from __future__ import annotations

import re

# Matches a medication entry line: Name dose frequency [date]
RE_MED_ENTRY = re.compile(
    r"(?P<name>[A-Za-z][\w\-]+)"
    r"(?:\s+(?P<dose>\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|units?|iu|tab|cap)s?))"
    r"(?:\s+(?P<freq>\bqd\b|\bq\.?d\.?\b|\bbid\b|\btid\b|\bqid\b|\bprn\b"
    r"|\bdaily\b|\bweekly\b|\bmonthly\b|\bonce\b|\btwice\b|\bonce daily\b"
    r"|\btwice daily\b|\bthree times\b))?",
    re.IGNORECASE,
)

RE_ORDER_TYPE = re.compile(
    r"\b(standing|routine|prn|as needed|stat|immediate)\b",
    re.IGNORECASE,
)

RE_MED_DATE = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"
)


def parse_medications(section_text: str) -> list[dict]:
    """
    Return a list of parsed medication entries.
    Each dict has keys: name, dose, freq, order_type, date, raw_line.
    Fields may be None if not found.
    """
    results: list[dict] = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = RE_MED_ENTRY.search(line)
        if not m:
            continue
        ot = RE_ORDER_TYPE.search(line)
        dt = RE_MED_DATE.search(line)
        results.append({
            "name":       m.group("name"),
            "dose":       m.group("dose"),
            "freq":       m.group("freq"),
            "order_type": ot.group(1) if ot else None,
            "date":       dt.group(1) if dt else None,
            "raw_line":   line,
        })
    return results


def section_mentions_medications(text: str) -> bool:
    """True if the note body references any medication discussion."""
    return bool(re.search(
        r"\b(medic(?:ation|ine)|prescri(?:bed|ption)|pharmacy|refill|"
        r"medication\s+management|psych\s+meds|psychiatric\s+medication)\b",
        text,
        re.IGNORECASE,
    ))
