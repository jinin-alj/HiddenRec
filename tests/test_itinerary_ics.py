"""Tests for itinerary models and ICS export."""

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from itinerary_models import (
    DayPlan,
    ItineraryPlan,
    ScheduleBlock,
    TripParameters,
    parse_hhmm,
)
from ics_export import default_ics_filename, write_itinerary_ics


def test_trip_parameters_validation():
    t = TripParameters(
        city="Madrid",
        start_date=date(2026, 6, 1),
        num_days=3,
        budget_amount=500,
        currency="EUR",
        food_focused=True,
        timezone="Europe/Madrid",
    )
    assert t.city == "Madrid"


def test_schedule_block_normalizes_time():
    b = ScheduleBlock(start="9:5", end="10:00", title="Coffee", kind="breakfast")
    assert b.start == "09:05"
    assert b.end == "10:00"


def test_write_itinerary_ics_creates_events(tmp_path):
    plan = ItineraryPlan(
        city="Madrid",
        country_hint="Spain",
        season="summer",
        days=[
            DayPlan(
                date="2026-06-01",
                blocks=[
                    ScheduleBlock(
                        start="09:00",
                        end="10:30",
                        title="Brunch at Casa Test",
                        description="Try churros",
                        kind="brunch",
                    )
                ],
            )
        ],
    )
    out = tmp_path / "t.ics"
    write_itinerary_ics(plan, out, "Europe/Madrid")
    text = out.read_text(encoding="utf-8")
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "SUMMARY:Brunch at Casa Test" in text
    assert "END:VEVENT" in text
    assert "END:VCALENDAR" in text
    assert re.search(r"DTSTART:\d{8}T\d{6}Z", text)


def test_default_ics_filename():
    assert "hiddenrec" in default_ics_filename("Madrid", date(2026, 4, 1))


def test_parse_hhmm():
    assert parse_hhmm("14:30").hour == 14 and parse_hhmm("14:30").minute == 30
