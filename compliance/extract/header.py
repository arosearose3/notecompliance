"""
Extract structured header fields from the first page of a note.

All regex constants are compiled once at import time.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

from compliance.models import HeaderFields

# ── date / time ──────────────────────────────────────────────────────────────

RE_DATE_TIME = re.compile(
    r"Date and Time:\s+"
    r"(\d{1,2}/\d{1,2}/\d{4})"          # date group 1
    r"(?:\s+(\d{1,2}:\d{2}\s*[AP]M)"    # optional start group 2
    r"\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?" # optional end   group 3
)

RE_ENTRY_DATE = re.compile(
    r"(?:Entry Date|Note Created|Signed on|Date Signed):\s+"
    r"(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)

# ── clinician / supervisor ───────────────────────────────────────────────────

RE_CLINICIAN = re.compile(
    r"Clinician:\s+([^,\n]+),\s*(\S+)"
)
RE_SUPERVISOR = re.compile(
    r"Supervisor:\s+([^,\n]+),\s*(\S+)"
)

# ── duration ─────────────────────────────────────────────────────────────────

RE_DURATION = re.compile(
    r"Duration:\s+(\d+)\s*minutes?",
    re.IGNORECASE,
)

# ── member ───────────────────────────────────────────────────────────────────

RE_PATIENT = re.compile(
    r"Patient:\s+([^\n]+)"
)
RE_DOB = re.compile(
    r"(?:DOB|Date of Birth):\s+(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)

# ── location / service code ──────────────────────────────────────────────────

RE_LOCATION = re.compile(
    r"Location:\s+([^\n]+)",
    re.IGNORECASE,
)
RE_SERVICE_CODE = re.compile(
    r"Service Code:\s+(\d{5}(?:[A-Z]{2})?)",
    re.IGNORECASE,
)

# ── participants ─────────────────────────────────────────────────────────────

RE_PARTICIPANTS = re.compile(
    r"Participants?:\s+([^\n]+)",
    re.IGNORECASE,
)

# ── license in signature block ───────────────────────────────────────────────

RE_LICENSE = re.compile(
    r"License\s+([A-Z]{2})\s+(\d+)"
)


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def _parse_time(s: str) -> time | None:
    s = s.strip().upper().replace(" ", "")
    for fmt in ("%I:%M%p", "%I:%M %p"):
        try:
            return datetime.strptime(s, fmt.replace(" ", "")).time()
        except ValueError:
            pass
    return None


def extract_header(text: str) -> HeaderFields:
    h = HeaderFields()

    m = RE_DATE_TIME.search(text)
    if m:
        h.service_date = _parse_date(m.group(1))
        if m.group(2):
            h.start_time = _parse_time(m.group(2))
        if m.group(3):
            h.end_time = _parse_time(m.group(3))

    m = RE_ENTRY_DATE.search(text)
    if m:
        h.entry_date = _parse_date(m.group(1))

    m = RE_CLINICIAN.search(text)
    if m:
        h.clinician = m.group(1).strip()
        h.clinician_credential = m.group(2).strip()

    m = RE_SUPERVISOR.search(text)
    if m:
        h.supervisor = m.group(1).strip()

    m = RE_DURATION.search(text)
    if m:
        try:
            h.duration_minutes = int(m.group(1))
        except ValueError:
            pass

    if h.start_time and h.end_time:
        start_dt = datetime.combine(date.today(), h.start_time)
        end_dt = datetime.combine(date.today(), h.end_time)
        delta = (end_dt - start_dt).seconds // 60
        if 0 < delta < 600 and h.duration_minutes is None:
            h.duration_minutes = delta

    m = RE_PATIENT.search(text)
    if m:
        raw = m.group(1).strip()
        # Strip trailing merged fields (two-column layout merges on one line)
        for stopper in ("DOB:", "DOB ", "Location:", "Service Code:", "Participants:"):
            if stopper in raw:
                raw = raw.split(stopper)[0].strip()
                break
        h.member_name = raw.rstrip(",; \t")

    m = RE_DOB.search(text)
    if m:
        h.member_dob = _parse_date(m.group(1))

    m = RE_LOCATION.search(text)
    if m:
        h.location = m.group(1).strip()

    m = RE_SERVICE_CODE.search(text)
    if m:
        h.service_code = m.group(1).strip()

    m = RE_PARTICIPANTS.search(text)
    if m:
        raw = m.group(1).strip()
        h.participants = [p.strip() for p in raw.split(",") if p.strip()]

    # License from signature block (last page)
    lm = RE_LICENSE.search(text)
    if lm:
        h.license_state = lm.group(1)
        h.license_id = lm.group(2)

    return h
