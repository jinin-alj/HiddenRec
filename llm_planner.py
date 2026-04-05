"""Build a validated itinerary from scraped text using OpenAI or local Ollama."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI

from itinerary_models import DayPlan, ItineraryPlan, ScheduleBlock, TripParameters
from scraped_types import ScrapedResult

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH, override=False)

logger = logging.getLogger(__name__)

BACKEND_OPENAI = "openai"
BACKEND_OLLAMA = "ollama"

ENV_BACKEND = "HIDDENREC_LLM_BACKEND"
ENV_MODEL = "HIDDENREC_LLM_MODEL"
ENV_API_KEY = "OPENAI_API_KEY"
ENV_OLLAMA_BASE = "HIDDENREC_OLLAMA_BASE_URL"
ENV_OLLAMA_MODEL = "HIDDENREC_OLLAMA_MODEL"
ENV_TIMEOUT_READ = "HIDDENREC_LLM_TIMEOUT_SECONDS"
ENV_OLLAMA_MAX_CORPUS = "HIDDENREC_OLLAMA_MAX_CORPUS_CHARS"

DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434/v1"
DEFAULT_READ_TIMEOUT_S = 300.0
DEFAULT_OLLAMA_MAX_CORPUS = 12_000

MAX_CORPUS_CHARACTERS = 100_000
OLLAMA_PLACEHOLDER_KEY = "ollama"
MAX_LLM_ATTEMPTS = 3
MAX_BLOCKS_PER_DAY = 8

DEBUG_DIR = Path(__file__).resolve().parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

NORMAL_SLOTS: list[tuple[str, str, str]] = [
    ("breakfast", "08:00", "09:30"),
    ("activity", "09:30", "12:00"),
    ("lunch", "12:30", "14:30"),
    ("activity", "14:30", "17:30"),
    ("snack", "17:30", "18:30"),
    ("activity", "18:30", "20:00"),
    ("dinner", "20:00", "22:00"),
]

FOOD_SLOTS: list[tuple[str, str, str]] = [
    ("breakfast", "08:00", "09:30"),
    ("lunch", "12:30", "14:30"),
    ("snack", "17:00", "18:00"),
    ("dinner", "20:00", "22:00"),
]

FREE_ACTIVITY_KEYWORDS = {
    "park",
    "plaza",
    "square",
    "garden",
    "walk",
    "stroll",
    "market",
    "street",
    "viewpoint",
    "mirador",
    "free",
    "self-guided",
    "neighborhood",
    "cathedral exterior",
}

SEASON_BAD_KEYWORDS: dict[str, set[str]] = {
    "spring": {
        "ski",
        "snowboard",
        "christmas market",
        "christmas fair",
        "ice skating",
        "winter village",
        "sledding",
        "beach club",
        "pool party",
        "sunbed",
    },
    "summer": {
        "ski",
        "snowboard",
        "christmas market",
        "christmas fair",
        "ice skating",
        "winter village",
        "sledding",
    },
    "autumn": {
        "ski",
        "snowboard",
        "christmas market",
        "christmas fair",
        "ice skating",
        "winter village",
        "pool party",
        "beach club",
    },
    "winter": {
        "beach club",
        "pool party",
        "sunbed",
        "summer festival",
        "sunbathing",
        "open-air pool",
        "rooftop pool",
    },
}

MEAL_DEFAULT_COSTS = {
    "breakfast": 10.0,
    "snack": 8.0,
    "lunch": 18.0,
    "dinner": 28.0,
    "meal": 20.0,
    "activity": 10.0,
    "sightseeing": 12.0,
}

FOOD_CATEGORY_KEYWORDS = {
    "restaurant",
    "cafe",
    "café",
    "bakery",
    "bar",
    "market",
    "food",
    "brunch",
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "eat",
    "tapas",
    "chocolate",
}

ACTIVITY_CATEGORY_KEYWORDS = {
    "museum",
    "gallery",
    "landmark",
    "park",
    "palace",
    "garden",
    "church",
    "cathedral",
    "square",
    "plaza",
    "neighborhood",
    "street",
    "viewpoint",
    "market",
    "monument",
    "activity",
    "sightseeing",
    "walk",
}


def get_llm_backend() -> str:
    explicit = os.environ.get(ENV_BACKEND, "").strip().lower()
    if explicit == BACKEND_OPENAI:
        return BACKEND_OPENAI
    if explicit == BACKEND_OLLAMA:
        return BACKEND_OLLAMA
    if os.environ.get(ENV_API_KEY, "").strip():
        return BACKEND_OPENAI
    return BACKEND_OLLAMA


def is_llm_configured() -> bool:
    if get_llm_backend() == BACKEND_OLLAMA:
        return True
    key = os.environ.get(ENV_API_KEY, "")
    return bool(key and key.strip())


def describe_llm_run_settings() -> str:
    return (
        f"backend={get_llm_backend()}, "
        f"model={_resolve_model_name()}, "
        f"read_timeout_s={int(_read_timeout_seconds())}"
    )


def _read_timeout_seconds() -> float:
    try:
        return max(30.0, float(os.environ.get(ENV_TIMEOUT_READ, DEFAULT_READ_TIMEOUT_S)))
    except ValueError:
        return DEFAULT_READ_TIMEOUT_S


def _max_corpus_chars() -> int:
    if get_llm_backend() == BACKEND_OLLAMA:
        try:
            return max(
                4000,
                min(
                    int(os.environ.get(ENV_OLLAMA_MAX_CORPUS, DEFAULT_OLLAMA_MAX_CORPUS)),
                    MAX_CORPUS_CHARACTERS,
                ),
            )
        except ValueError:
            return DEFAULT_OLLAMA_MAX_CORPUS
    return MAX_CORPUS_CHARACTERS


def _resolve_model_name() -> str:
    if get_llm_backend() == BACKEND_OLLAMA:
        return os.environ.get(
            ENV_OLLAMA_MODEL,
            os.environ.get(ENV_MODEL, DEFAULT_OLLAMA_MODEL),
        ).strip()
    return os.environ.get(ENV_MODEL, DEFAULT_LLM_MODEL).strip()


def _create_client() -> OpenAI:
    timeout = httpx.Timeout(
        connect=20.0,
        read=_read_timeout_seconds(),
        write=120.0,
        pool=20.0,
    )

    if get_llm_backend() == BACKEND_OLLAMA:
        base = os.environ.get(ENV_OLLAMA_BASE, DEFAULT_OLLAMA_BASE).strip().rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return OpenAI(
            base_url=base,
            api_key=OLLAMA_PLACEHOLDER_KEY,
            timeout=timeout,
        )

    key = os.environ.get(ENV_API_KEY, "").strip()
    if not key:
        raise RuntimeError(
            f"Set {ENV_API_KEY} for cloud OpenAI, or set "
            f"{ENV_BACKEND}={BACKEND_OLLAMA} for local Ollama."
        )
    return OpenAI(api_key=key, timeout=timeout)


def create_llm_client() -> OpenAI:
    return _create_client()


def _truncate_corpus(results: list[ScrapedResult], max_chars: int) -> str:
    lines: list[str] = []
    total = 0
    for item in results:
        line = f"[{item.platform}] {item.text}\n"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "".join(lines)


def _extract_json_object(raw: str) -> str:
    if not raw or not raw.strip():
        raise ValueError("The model returned an empty response.")

    text = raw.strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if fence_match:
        inner = fence_match.group(1).strip()
        try:
            json.loads(inner)
            return inner
        except json.JSONDecodeError:
            pass

    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        span = raw[first_brace:last_brace + 1]
        try:
            json.loads(span)
            return span
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract valid JSON from model output. First 300 chars: {raw[:300]!r}"
    )


def _unwrap_content_wrapper(payload: Any) -> Any:
    if isinstance(payload, dict) and "city" not in payload and "content" in payload:
        content = payload["content"]

        if isinstance(content, str) and content.strip():
            return json.loads(_extract_json_object(content))

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
                    elif isinstance(part.get("content"), str):
                        text_parts.append(part["content"])
                elif isinstance(part, str):
                    text_parts.append(part)

            joined = "\n".join(text_parts).strip()
            if joined:
                return json.loads(_extract_json_object(joined))

    return payload


def _exception_chain(exc: BaseException | None) -> list[BaseException]:
    out: list[BaseException] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        out.append(exc)
        nxt = exc.__cause__ if exc.__cause__ is not None else exc.__context__
        exc = nxt
    return out


def _is_connection_or_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True

    for err in _exception_chain(exc):
        if isinstance(
            err,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
            ),
        ):
            return True
    return False


def _chat_completion(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
):
    kwargs = dict(
        model=model,
        temperature=0.0,
        messages=messages,
    )

    if get_llm_backend() == BACKEND_OLLAMA:
        try:
            return client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            if _is_connection_or_timeout_error(exc):
                logger.error(
                    "Ollama unreachable or timed out (%s). Ensure Ollama is running "
                    "and HIDDENREC_OLLAMA_BASE_URL is correct.",
                    exc,
                )
                raise
            logger.warning(
                "Ollama JSON mode failed (%s); retrying without response_format.",
                exc,
            )
            return client.chat.completions.create(**kwargs)

    return client.chat.completions.create(
        **kwargs,
        response_format={"type": "json_object"},
    )


def _season_label(start_date: date) -> str:
    month = start_date.month
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _parse_cost_hint(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.lower().replace(",", ".")
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    if not numbers:
        return None
    if len(numbers) >= 2 and ("-" in cleaned or "to" in cleaned):
        return round((numbers[0] + numbers[1]) / 2.0, 2)
    return float(numbers[0])


def _patch_missing_fields(payload: dict, trip: TripParameters) -> dict:
    payload.setdefault("city", trip.city)
    payload.setdefault("country_hint", trip.country_hint or "")
    payload.setdefault("season", "")
    payload.setdefault("budget_notes", "")
    payload.setdefault("places", [])
    payload.setdefault("days", [])
    return payload


def _write_debug(name: str, content: str) -> None:
    try:
        (DEBUG_DIR / name).write_text(content, encoding="utf-8")
    except OSError:
        logger.warning("Could not write debug file %s", name)


def _prompt_day_schema(trip: TripParameters) -> str:
    if trip.food_focused:
        return """
  "days": [
    {
      "date": "YYYY-MM-DD",
      "blocks": [
        {"start": "08:00", "end": "09:30", "title": "Real breakfast venue", "description": "Short reason.", "kind": "breakfast"},
        {"start": "12:30", "end": "14:30", "title": "Real lunch venue", "description": "Short reason.", "kind": "lunch"},
        {"start": "17:00", "end": "18:00", "title": "Real snack / cafe venue", "description": "Short reason.", "kind": "snack"},
        {"start": "20:00", "end": "22:00", "title": "Real dinner venue", "description": "Short reason.", "kind": "dinner"}
      ]
    }
  ]
"""
    return """
  "days": [
    {
      "date": "YYYY-MM-DD",
      "blocks": [
        {"start": "08:00", "end": "09:30", "title": "Real breakfast venue", "description": "Short reason.", "kind": "breakfast"},
        {"start": "09:30", "end": "12:00", "title": "Real place to visit", "description": "Short reason.", "kind": "activity"},
        {"start": "12:30", "end": "14:30", "title": "Real lunch venue", "description": "Short reason.", "kind": "lunch"},
        {"start": "14:30", "end": "17:30", "title": "Real place to visit", "description": "Short reason.", "kind": "activity"},
        {"start": "17:30", "end": "18:30", "title": "Real snack / cafe venue", "description": "Short reason.", "kind": "snack"},
        {"start": "18:30", "end": "20:00", "title": "Real place to visit", "description": "Short reason.", "kind": "activity"},
        {"start": "20:00", "end": "22:00", "title": "Real dinner venue", "description": "Short reason.", "kind": "dinner"}
      ]
    }
  ]
"""


def _build_prompt(trip: TripParameters, corpus: str) -> str:
    season = _season_label(trip.start_date)
    dates = [(trip.start_date + timedelta(days=i)).isoformat() for i in range(trip.num_days)]
    dates_list = ", ".join(dates)

    if trip.food_focused:
        rules = """
Mode: FOOD ONLY
- Each day must have exactly 4 blocks.
- Only breakfast, lunch, snack, dinner.
- No museums, parks, sightseeing, neighborhoods, shopping, or generic activities.
- Use real food venues.
"""
    else:
        rules = """
Mode: FULL ITINERARY
- Each day must have exactly 7 blocks.
- Include breakfast, 3 activity/sightseeing stops, lunch, snack, and dinner.
- Use real places and real food venues.
- Make days feel different from each other.
"""

    return f"""Plan a {trip.num_days}-day trip to {trip.city}.
Dates: {dates_list}
Season: {season}
Budget limit: {trip.budget_amount} {trip.currency}

Use these ideas from social posts:
{corpus or "(No posts were collected. Still create a reasonable itinerary.)"}

Reply with ONLY one JSON object in this exact structure:
{{
  "city": "{trip.city}",
  "country_hint": "{trip.country_hint}",
  "season": "{season}",
  "budget_notes": "One short note about keeping costs reasonable.",
  "places": [
    {{
      "name": "Real place name",
      "category": "restaurant or museum or landmark",
      "rough_cost_hint": "15 {trip.currency}",
      "source_urls": []
    }}
  ],
{_prompt_day_schema(trip)}
}}

Hard rules:
- City must remain exactly {trip.city}
- Include exactly {trip.num_days} day objects with these dates: {dates_list}
- Prefer activities suitable for {season} or season-neutral
- Stay within the total budget as best as possible
- Use real specific venue names, not placeholders
- Output only JSON, no markdown, no commentary
{rules}
"""


def _same_city(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def _block_text(block: ScheduleBlock) -> str:
    return f"{block.title} {block.description} {block.kind}".lower()


def _is_bad_for_season(text: str, season: str) -> bool:
    for keyword in SEASON_BAD_KEYWORDS.get(season, set()):
        if keyword in text:
            return True
    return False


def _looks_foodish(text: str) -> bool:
    return any(keyword in text for keyword in FOOD_CATEGORY_KEYWORDS)


def _looks_activityish(text: str) -> bool:
    return any(keyword in text for keyword in ACTIVITY_CATEGORY_KEYWORDS)


def _infer_kind(kind: str, title: str, description: str) -> str:
    base = (kind or "").strip().lower()
    text = f"{title} {description} {kind}".lower()

    if "breakfast" in text or "brunch" in text:
        return "breakfast"
    if "lunch" in text:
        return "lunch"
    if "dinner" in text:
        return "dinner"
    if "snack" in text or "coffee" in text or "cafe" in text or "café" in text:
        return "snack"
    if base in {"breakfast", "lunch", "dinner", "snack", "meal", "activity", "sightseeing"}:
        return base
    if _looks_foodish(text):
        return "meal"
    return "activity"


def _candidate_score(required_kind: str, title: str, description: str, kind: str) -> int:
    inferred = _infer_kind(kind, title, description)
    text = f"{title} {description}".lower()

    score = 0

    if required_kind == "activity":
        if inferred in {"activity", "sightseeing"}:
            score += 4
        elif inferred not in {"breakfast", "lunch", "dinner", "snack", "meal"}:
            score += 3
        if _looks_activityish(text):
            score += 3
        if _looks_foodish(text):
            score -= 3
    else:
        if inferred == required_kind:
            score += 5
        elif inferred == "meal":
            score += 3
        if _looks_foodish(text):
            score += 3
        if _looks_activityish(text) and required_kind != "activity":
            score -= 2

    if title and len(title.strip()) >= 4:
        score += 1

    return score


def _estimated_block_cost(block: ScheduleBlock, place_costs: dict[str, float]) -> float:
    title_key = block.title.strip().lower()
    if title_key in place_costs:
        return place_costs[title_key]

    text = _block_text(block)
    if any(keyword in text for keyword in FREE_ACTIVITY_KEYWORDS):
        return 0.0

    inferred = _infer_kind(block.kind, block.title, block.description)
    return MEAL_DEFAULT_COSTS.get(inferred, 10.0)


def _collect_place_costs(plan: ItineraryPlan) -> dict[str, float]:
    out: dict[str, float] = {}
    for place in plan.places:
        cost = _parse_cost_hint(place.rough_cost_hint)
        if cost is not None:
            out[place.name.strip().lower()] = cost
    return out


def _total_estimated_cost(plan: ItineraryPlan) -> float:
    place_costs = _collect_place_costs(plan)
    total = 0.0
    for day in plan.days:
        for block in day.blocks:
            total += _estimated_block_cost(block, place_costs)
    return round(total, 2)


def _fallback_title(city: str, required_kind: str, index: int) -> str:
    if required_kind == "breakfast":
        return f"Breakfast in {city}"
    if required_kind == "lunch":
        return f"Lunch in {city}"
    if required_kind == "dinner":
        return f"Dinner in {city}"
    if required_kind == "snack":
        return f"Snack in {city}"
    labels = [
        f"Morning walk in {city}",
        f"Afternoon stop in {city}",
        f"Evening stroll in {city}",
    ]
    return labels[min(index, len(labels) - 1)]


def _fallback_description(city: str, required_kind: str) -> str:
    if required_kind == "activity":
        return f"General activity slot in {city}."
    return f"{required_kind.title()} stop in {city}."


def _slot_template(trip: TripParameters) -> list[tuple[str, str, str]]:
    return FOOD_SLOTS if trip.food_focused else NORMAL_SLOTS


def _build_candidate_blocks(plan: ItineraryPlan, trip: TripParameters) -> list[ScheduleBlock]:
    season = _season_label(trip.start_date)
    candidates: list[ScheduleBlock] = []

    for day in plan.days:
        for block in day.blocks:
            if not block.title.strip():
                continue
            if _is_bad_for_season(_block_text(block), season):
                continue
            candidates.append(
                ScheduleBlock(
                    start=block.start,
                    end=block.end,
                    title=block.title.strip(),
                    description=block.description.strip(),
                    kind=block.kind,
                )
            )

    for place in plan.places:
        title = place.name.strip()
        if not title:
            continue
        description = "Recommended place"
        if place.category.strip():
            description = f"{place.category.strip()}."
        if place.rough_cost_hint.strip():
            description += f" Cost hint: {place.rough_cost_hint.strip()}."
        text = f"{title} {description}".lower()
        if _is_bad_for_season(text, season):
            continue
        inferred_kind = "meal" if _looks_foodish(text) else "activity"
        candidates.append(
            ScheduleBlock(
                start="09:00",
                end="10:00",
                title=title,
                description=description,
                kind=inferred_kind,
            )
        )

    deduped: list[ScheduleBlock] = []
    seen: set[str] = set()
    for block in candidates:
        key = block.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(block)

    return deduped


def _pick_best_candidate(
    candidates: list[ScheduleBlock],
    required_kind: str,
    used_titles: set[str],
) -> ScheduleBlock | None:
    scored: list[tuple[int, ScheduleBlock]] = []

    for block in candidates:
        key = block.title.strip().lower()
        if key in used_titles:
            continue
        score = _candidate_score(required_kind, block.title, block.description, block.kind)
        if score > 0:
            scored.append((score, block))

    if not scored:
        return None

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def _repair_plan(plan: ItineraryPlan, trip: TripParameters) -> ItineraryPlan:
    templates = _slot_template(trip)
    candidates = _build_candidate_blocks(plan, trip)
    repaired_days: list[DayPlan] = []

    place_costs = _collect_place_costs(plan)
    global_used_titles: set[str] = set()

    for day_index in range(trip.num_days):
        day_date = (trip.start_date + timedelta(days=day_index)).isoformat()
        day_blocks: list[ScheduleBlock] = []
        local_used_titles: set[str] = set()

        activity_index = 0

        for required_kind, start, end in templates:
            chosen = _pick_best_candidate(candidates, required_kind, global_used_titles | local_used_titles)

            if chosen is None and required_kind == "activity":
                chosen = _pick_best_candidate(candidates, "activity", global_used_titles | local_used_titles)

            if chosen is None:
                title = _fallback_title(trip.city, required_kind, activity_index)
                description = _fallback_description(trip.city, required_kind)
            else:
                title = chosen.title.strip()
                description = chosen.description.strip()
                local_used_titles.add(title.lower())

            if required_kind == "activity":
                activity_index += 1

            day_blocks.append(
                ScheduleBlock(
                    start=start,
                    end=end,
                    title=title,
                    description=description,
                    kind=required_kind,
                )
            )

        repaired_days.append(DayPlan(date=day_date, blocks=day_blocks))
        global_used_titles.update(local_used_titles)

    repaired = ItineraryPlan(
        city=trip.city,
        country_hint=plan.country_hint or trip.country_hint,
        season=_season_label(trip.start_date),
        budget_notes=plan.budget_notes or f"Estimated total: {_total_estimated_cost(plan):.2f} {trip.currency}",
        places=plan.places,
        days=repaired_days,
    )

    total_cost = _total_estimated_cost(repaired)
    if total_cost > trip.budget_amount:
        repaired.budget_notes = (
            f"Estimated total may exceed budget ({total_cost:.2f} {trip.currency} "
            f"vs {trip.budget_amount:.2f} {trip.currency}). Prefer cheaper alternatives."
        )

    return repaired


def _payload_to_plan(payload: dict, trip: TripParameters) -> ItineraryPlan:
    payload = _patch_missing_fields(payload, trip)

    raw_city = _clean_text(payload.get("city"), trip.city)
    if raw_city and not _same_city(raw_city, trip.city):
        raise ValueError(f"Model drifted to wrong city: {raw_city!r} instead of {trip.city!r}")

    plan = ItineraryPlan.model_validate(payload)
    return _repair_plan(plan, trip)


def build_itinerary_with_llm(
    trip: TripParameters,
    scraped: list[ScrapedResult],
    *,
    model: str | None = None,
) -> ItineraryPlan:
    client = _create_client()
    resolved_model = (model or _resolve_model_name()).strip()
    corpus = _truncate_corpus(scraped, _max_corpus_chars())
    prompt = _build_prompt(trip, corpus)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a travel planner. Output only valid JSON. "
                "No markdown. No commentary."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    last_error: Exception | None = None

    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        raw = ""
        try:
            completion = _chat_completion(client, resolved_model, messages)
            raw = completion.choices[0].message.content or ""
            raw = raw.strip()

            if not raw:
                raise RuntimeError("The model returned an empty response.")

            _write_debug(f"attempt_{attempt}_raw_text.txt", raw)

            extracted = _extract_json_object(raw)
            payload = json.loads(extracted)
            payload = _unwrap_content_wrapper(payload)

            _write_debug(
                f"attempt_{attempt}_raw_payload.json",
                json.dumps(payload, indent=2, ensure_ascii=False),
            )

            final_plan = _payload_to_plan(payload, trip)

            _write_debug(
                f"attempt_{attempt}_final_plan.json",
                final_plan.model_dump_json(indent=2),
            )

            return final_plan

        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM attempt %d/%d failed: %s. raw[:400]=%r",
                attempt,
                MAX_LLM_ATTEMPTS,
                exc,
                raw[:400],
            )

            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous JSON failed because: {exc}\n"
                        f"Keep the city exactly as {trip.city}.\n"
                        "Output only corrected JSON.\n"
                    ),
                }
            )

    raise last_error or RuntimeError("The language model did not return a valid itinerary.")