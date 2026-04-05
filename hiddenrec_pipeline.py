"""End-to-end pipeline: scrape social posts, plan with an LLM, write an ICS file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from hiddenrec import build_search_queries, create_driver, run_all_scrapers
from ics_export import default_ics_filename, write_itinerary_ics
from itinerary_models import TripParameters
from llm_planner import build_itinerary_with_llm, describe_llm_run_settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, float], None]


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def default_exports_dir() -> Path:
    """Folder next to the project where calendar files are written."""
    path = _project_root() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_hiddenrec_pipeline(
    trip: TripParameters,
    log: Callable[[str], None],
    on_progress: ProgressCallback | None = None,
) -> Path:
    """
    Scrape social posts, ask the LLM to build an itinerary, and write an ICS file.
    Any exception is allowed to propagate so the caller can display it clearly.
    """
    def tick(phase: str, fraction: float) -> None:
        if on_progress is not None:
            on_progress(phase, max(0.0, min(1.0, fraction)))

    tick("scraping", 0.05)
    log("Collecting posts from Reddit, TikTok, and Pinterest.")

    driver = create_driver()
    try:
        queries = build_search_queries(trip)
        results = run_all_scrapers(driver, trip, queries)
    finally:
        driver.quit()

    tick("scraping", 0.50)
    log(f"Collected {len(results)} snippets.")

    tick("llm", 0.55)
    log("Building your itinerary with the language model.")
    log(f"Planner settings: {describe_llm_run_settings()}")
    log("This can take several minutes on a local model. Please wait.")

    plan = build_itinerary_with_llm(trip, results)
    tick("llm", 0.88)
    log(f"Plan complete: {len(plan.days)} days, {sum(len(d.blocks) for d in plan.days)} blocks.")

    tick("save", 0.92)
    filename = default_ics_filename(trip.city, trip.start_date)
    output_path = default_exports_dir() / filename
    write_itinerary_ics(plan, output_path, trip.timezone)
    tick("done", 1.0)
    log(f"Saved calendar file: {output_path}")
    return output_path