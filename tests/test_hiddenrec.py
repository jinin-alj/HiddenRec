"""Unit tests for HiddenRec (no live browser required)."""

import os
import sys

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hiddenrec as hr


def test_build_search_queries_food_and_explorer():
    food = hr.Config(
        city="San Francisco",
        food_mode=True,
        instagram_login=False,
    )
    q_food = hr.build_search_queries(food)
    assert "reddit" in q_food and "instagram_hashtags" in q_food
    assert any("food" in t.lower() for t in q_food["instagram_hashtags"])

    explore = hr.Config(
        city="New York",
        food_mode=False,
        instagram_login=False,
    )
    q_exp = hr.build_search_queries(explore)
    assert any("travel" in t or "visit" in t or "hidden" in t for t in q_exp["instagram_hashtags"])


def test_build_scraped_result_filters_short_text():
    assert hr.build_scraped_result("X", "hi", "u") is None
    r = hr.build_scraped_result("X", "hello world", "https://e")
    assert r is not None and r.text == "hello world"


def test_place_extractor_trigger_and_ranking():
    ext = hr.PlaceExtractor()
    ext.process_result(
        hr.ScrapedResult(
            platform="Instagram",
            text="You must visit Tartine Bakery when in town.",
            url="https://example.com",
        )
    )
    ranked = ext.get_ranked_places()
    assert ranked, "expected at least one place from trigger phrase"
    names = [n for n, _ in ranked]
    assert any("Tartine" in n or "Bakery" in n for n in names)


def test_find_elements_by_first_matching_selector_requires_driver():
    """Document: selector helper is used by scrapers; logic is trivial."""
    class FakeDriver:
        def find_elements(self, by, selector):
            if "first" in selector:
                return [object()]
            return []

    d = FakeDriver()
    found = hr.find_elements_by_first_matching_selector(
        d, ["span.nope", "div.first"]
    )
    assert len(found) == 1


def test_run_all_scrapers_always_includes_instagram(monkeypatch):
    """Instagram hashtag scraping must run even when login is disabled."""
    calls = {"instagram": 0}

    def fake_scrape_reddit(driver, queries):
        return []

    def fake_scrape_tiktok(driver, queries):
        return []

    def fake_scrape_pinterest(driver, queries):
        return []

    def fake_scrape_instagram(driver, config, hashtags):
        calls["instagram"] += 1
        return []

    monkeypatch.setattr(hr, "scrape_reddit", fake_scrape_reddit)
    monkeypatch.setattr(hr, "scrape_tiktok", fake_scrape_tiktok)
    monkeypatch.setattr(hr, "scrape_pinterest", fake_scrape_pinterest)
    monkeypatch.setattr(hr, "scrape_instagram", fake_scrape_instagram)

    cfg = hr.Config(
        city="Test",
        food_mode=False,
        instagram_login=False,
    )
    queries = hr.build_search_queries(cfg)
    hr.run_all_scrapers(None, cfg, queries)
    assert calls["instagram"] == 1
