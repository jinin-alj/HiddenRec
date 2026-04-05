"""Tests for LLM itinerary planning with a mocked OpenAI compatible client."""

import json
import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from itinerary_models import TripParameters
from llm_planner import build_itinerary_with_llm, create_llm_client
from scraped_types import ScrapedResult


def _trip():
    return TripParameters(
        city="Madrid",
        country_hint="Spain",
        start_date=date(2026, 6, 10),
        num_days=2,
        budget_amount=400,
        currency="EUR",
        food_focused=True,
        timezone="Europe/Madrid",
        locale_queries="auto",
    )


def test_build_itinerary_with_llm_parses_and_finalizes_days():
    sample_json = {
        "city": "Madrid",
        "country_hint": "Spain",
        "season": "summer",
        "budget_notes": "Roughly split across meals.",
        "places": [{"name": "Cafe Test", "category": "cafe", "rough_cost_hint": "10 EUR"}],
        "days": [
            {
                "date": "2026-06-10",
                "blocks": [
                    {
                        "start": "09:00",
                        "end": "10:00",
                        "title": "Breakfast",
                        "description": "Pastries",
                        "kind": "breakfast",
                    }
                ],
            }
        ],
    }

    fake_message = MagicMock()
    fake_message.content = json.dumps(sample_json)

    fake_choice = MagicMock()
    fake_choice.message = fake_message

    fake_completion = MagicMock()
    fake_completion.choices = [fake_choice]

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion

    scraped = [
        ScrapedResult(platform="TikTok", text="Sample caption about Madrid.", url="u1"),
    ]

    with patch("llm_planner.OpenAI", return_value=fake_client):
        plan = build_itinerary_with_llm(_trip(), scraped, model="llama3.1:8b")

    assert len(plan.days) == 2
    assert plan.days[0].date == "2026-06-10"
    assert plan.days[1].date == "2026-06-11"
    assert plan.city == "Madrid"


def test_create_llm_client_uses_ollama_base_url():
    env = {
        "HIDDENREC_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("llm_planner.OpenAI") as ctor:
            ctor.return_value = MagicMock()
            client = create_llm_client()
    assert client is not None
    kwargs = ctor.call_args.kwargs
    assert kwargs["base_url"] == "http://127.0.0.1:11434/v1"
    assert kwargs["api_key"] == "ollama"
    assert "timeout" in kwargs
