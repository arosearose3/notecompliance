"""
Standards B1–B2: Entry integrity.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from compliance.checks.base import (
    CheckResult, failed, manual_review, not_applicable, passed,
)

if TYPE_CHECKING:
    from compliance.judges.base import Judge
    from compliance.models import ContextBundle, Note

RE_LATE_ENTRY = re.compile(r"\blate\s+entry\b", re.IGNORECASE)


class CheckB1:
    """Late entry notation when service-to-entry gap > 24 h."""
    standard_id = "B1"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        svc = note.header.service_date
        entry = note.header.entry_date

        if not svc:
            return manual_review("B1", "Cannot verify: service date not extractable.")

        if not entry:
            # Try PDF creation date from file metadata (fallback)
            return manual_review(
                "B1",
                "Cannot verify late entry: entry/signing date not found in note text. "
                "Check PDF metadata or EHR timestamp.",
            )

        delta = datetime.combine(entry, datetime.min.time()) - datetime.combine(svc, datetime.min.time())
        if delta <= timedelta(hours=24):
            return not_applicable("B1", f"Entry within 24 h of service ({delta}).")

        if RE_LATE_ENTRY.search(note.full_text):
            return passed(
                "B1",
                f"Late entry phrase found (service {svc}, entry {entry}, delta {delta.days}d).",
                excerpts=[m.group() for m in RE_LATE_ENTRY.finditer(note.full_text)],
            )

        return failed(
            "B1",
            f"Entry is {delta.days} day(s) after service but 'late entry' notation missing. "
            f"Service date: {svc}, entry date: {entry}.",
        )


class CheckB2:
    """Modification audit trail — always manual_review (PDFs don't preserve this)."""
    standard_id = "B2"

    def run(self, note: "Note", judge: "Judge", bundle=None) -> CheckResult:
        return manual_review(
            "B2",
            "PDFs do not preserve in-place modification history. "
            "Verify the original EHR record for lined-through corrections "
            "that are dated and initialed.",
        )
