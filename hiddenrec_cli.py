"""Terminal interface for HiddenRec when the Tk desktop UI is not available."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from hiddenrec_pipeline import run_hiddenrec_pipeline
from itinerary_models import TripParameters


def run_cli_app() -> None:
    if len(sys.argv) <= 1:
        print(
            "Tkinter is not available on this Python build.\n"
            "Pass trip options on the command line, for example:\n"
            "  python hiddenrec.py --city Madrid --start 2026-06-01 --days 3\n"
            "Or use a Python install that includes Tcl/Tk (for example python.org).\n"
        )
        raise SystemExit(2)

    parser = argparse.ArgumentParser(
        description=(
            "HiddenRec without a GUI (use when tkinter is not installed). "
            "The planner uses local Ollama; see README for optional environment variables."
        ),
    )
    parser.add_argument("--city", required=True, help="Destination city")
    parser.add_argument(
        "--country",
        required=True,
        help="Country (for example Spain)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Trip start date as YYYY-MM-DD",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of days",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=500.0,
        help="Total trip budget",
    )
    parser.add_argument("--currency", default="EUR")
    parser.add_argument(
        "--food-focused",
        action="store_true",
        help="Prefer meal focused calendar slots",
    )
    parser.add_argument("--timezone", default="Europe/Madrid")
    parser.add_argument(
        "--locale",
        default="auto",
        choices=("auto", "en", "es"),
    )

    args = parser.parse_args()
    start_date = date.fromisoformat(args.start.strip())

    trip = TripParameters(
        city=args.city.strip(),
        country_hint=args.country.strip(),
        start_date=start_date,
        num_days=args.days,
        budget_amount=args.budget,
        currency=args.currency.strip(),
        food_focused=args.food_focused,
        timezone=args.timezone.strip(),
        locale_queries=args.locale.strip(),
    )

    def log(message: str) -> None:
        print(message, flush=True)

    run_hiddenrec_pipeline(trip, log)
