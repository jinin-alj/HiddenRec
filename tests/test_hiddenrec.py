import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hiddenrec as hr
from itinerary_models import TripParameters


def _base_trip(**overrides):
    params = dict(
        city="San Francisco",
        country_hint="",
        start_date=date(2026, 6, 1),
        num_days=3,
        budget_amount=1000,
        currency="USD",
        food_focused=False,
        timezone="America/Los_Angeles",
        locale_queries="en",
    )
    params.update(overrides)
    return TripParameters(**params)


def test_build_search_queries_food_and_explorer():
    food = _base_trip(food_focused=True, locale_queries="en")
    food_queries = hr.build_search_queries(food)
    assert "reddit" in food_queries and "tiktok" in food_queries
    assert "pinterest" in food_queries
    assert "instagram_hashtags" not in food_queries

    explore = _base_trip(food_focused=False, locale_queries="en")
    explore_queries = hr.build_search_queries(explore)
    assert "reddit" in explore_queries


def test_spanish_queries_merge_when_country_is_spain():
    trip = _base_trip(
        city="Madrid",
        country_hint="Spain",
        food_focused=False,
        locale_queries="auto",
    )
    queries = hr.build_search_queries(trip)
    flat = " ".join(queries["reddit"])
    assert "qué ver" in flat.lower() or "qué" in flat.lower()


def test_spanish_queries_merge_for_madrid_without_country_hint():
    trip = _base_trip(
        city="Madrid",
        country_hint="",
        food_focused=False,
        locale_queries="auto",
    )
    queries = hr.build_search_queries(trip)
    flat = " ".join(queries["reddit"])
    assert "qué ver" in flat.lower() or "qué" in flat.lower()


def test_build_scraped_result_filters_short_text():
    assert hr.build_scraped_result("X", "hi", "u") is None
    result = hr.build_scraped_result("X", "hello world", "https://example.com")
    assert result is not None and result.text == "hello world"


def test_find_elements_by_first_matching_selector_requires_driver():
    class FakeDriver:
        def find_elements(self, by, selector):
            if "first" in selector:
                return [object()]
            return []

    driver = FakeDriver()
    found = hr.find_elements_by_first_matching_selector(
        driver,
        ["span.nope", "div.first"],
    )
    assert len(found) == 1


def test_run_all_scrapers_three_platforms_only(monkeypatch):
    calls = {"reddit": 0, "tiktok": 0, "pinterest": 0}

    def fake_reddit(driver, queries):
        calls["reddit"] += 1
        return []

    def fake_tiktok(driver, queries):
        calls["tiktok"] += 1
        return []

    def fake_pinterest(driver, queries):
        calls["pinterest"] += 1
        return []

    monkeypatch.setattr(hr, "scrape_reddit", fake_reddit)
    monkeypatch.setattr(hr, "scrape_tiktok", fake_tiktok)
    monkeypatch.setattr(hr, "scrape_pinterest", fake_pinterest)

    trip = _base_trip(city="Test")
    queries = hr.build_search_queries(trip)
    hr.run_all_scrapers(None, trip, queries)
    assert calls == {"reddit": 1, "tiktok": 1, "pinterest": 1}
