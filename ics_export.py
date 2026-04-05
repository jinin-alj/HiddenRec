"""RFC 5545 iCalendar (.ics) export for HiddenRec itineraries."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from itinerary_models import ItineraryPlan, combine_local, parse_hhmm


def _escape_text(s: str) -> str:
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n")
    return s


def _utc_format(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def write_itinerary_ics(
    plan: ItineraryPlan,
    output_path: str | Path,
    timezone_name: str,
    calendar_name: str = "HiddenRec",
) -> Path:
    """
    Write VEVENTs for each schedule block. Times are interpreted in timezone_name
    and stored as UTC (Z) for broad client compatibility.
    """
    path = Path(output_path).expanduser()
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//HiddenRec//{calendar_name}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for day in plan.days:
        day_date = date.fromisoformat(day.date)
        for block in day.blocks:
            start_t = parse_hhmm(block.start)
            end_t = parse_hhmm(block.end)
            start_dt = combine_local(day_date, start_t, timezone_name)
            end_dt = combine_local(day_date, end_t, timezone_name)
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)

            uid = f"{uuid.uuid4()}@hiddenrec"
            desc_parts = [block.description.strip()] if block.description else []
            desc_parts.append(f"Kind: {block.kind}")
            if plan.city:
                desc_parts.append(f"City: {plan.city}")
            description = _escape_text("\n".join(desc_parts))

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{_utc_format(datetime.now(timezone.utc))}",
                    f"DTSTART:{_utc_format(start_dt)}",
                    f"DTEND:{_utc_format(end_dt)}",
                    f"SUMMARY:{_escape_text(block.title)}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                ]
            )

    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines) + "\r\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def default_ics_filename(city: str, start: date) -> str:
    safe = re.sub(r"[^\w\-]+", "_", city.strip().lower()).strip("_") or "trip"
    return f"hiddenrec_{safe}_{start.isoformat()}.ics"
