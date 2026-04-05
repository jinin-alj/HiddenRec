"""HiddenRec: Selenium scrapers for social platforms used by the itinerary pipeline."""

from __future__ import annotations

import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from itinerary_models import TripParameters
from scraped_types import ScrapedResult

MAX_POSTS_PER_QUERY = 12
MIN_TEXT_LENGTH = 5
SCROLL_DISTANCE_PX = 700
SCROLL_PAUSE_SECONDS = 1.5
PAGE_LOAD_SECONDS = 4
POST_ACTION_PAUSE_SECONDS = 2
TIKTOK_LOAD_SECONDS = 5

LOCALE_AUTO = "auto"
LOCALE_ENGLISH = "en"
LOCALE_SPANISH = "es"

SPAIN_COUNTRY_HINTS = frozenset({"spain", "españa", "espana"})

# Helps when the user enters a well known city without a country hint.
SPAIN_CITY_NAMES = frozenset(
    {
        "madrid",
        "barcelona",
        "valencia",
        "seville",
        "sevilla",
        "bilbao",
        "malaga",
        "málaga",
    }
)

REDDIT_SELECTORS = [
    "h3[class*='title']",
    "[data-testid='post-title']",
    "a[data-click-id='body'] h3",
    "shreddit-post",
]

TIKTOK_SELECTORS = [
    "[data-e2e='search-card-desc']",
    "[class*='DivInfoContainer'] p",
    "[class*='video-feed-item'] p",
    "p[class*='desc']",
    "[class*='StyledVideoFeedItemV2'] p",
]

COOKIE_ACCEPT_LABELS = ["accept all", "accept", "allow all", "agree", "ok"]

FOOD_RELEVANCE_KEYWORDS = {
    "breakfast", "brunch", "lunch", "dinner", "snack",
    "coffee", "cafe", "café", "restaurant", "eat",
    "food", "bakery", "pastry", "dessert", "tapas",
    "desayuno", "comida", "cena", "cafeteria", "cafetería",
    "pasteleria", "pastelería", "postre", "restaurante",
}

def _food_relevance_score(text: str) -> int:
    lowered = text.lower()
    return sum(1 for kw in FOOD_RELEVANCE_KEYWORDS if kw in lowered)

def should_include_spanish_queries(trip: TripParameters) -> bool:
    """Spanish query variants help for cities in Spain when locale is auto or es."""
    mode = trip.locale_queries.strip().lower()
    if mode == LOCALE_SPANISH:
        return True
    if mode == LOCALE_ENGLISH:
        return False
    hint = trip.country_hint.strip().lower()
    if hint in SPAIN_COUNTRY_HINTS:
        return True
    city_key = trip.city.strip().lower()
    return city_key in SPAIN_CITY_NAMES


def _merge_query_dicts(base: dict, extra: dict) -> dict:
    out = {key: list(values) for key, values in base.items()}
    for key, values in extra.items():
        out.setdefault(key, [])
        out[key].extend(values)
    return out


def _food_queries_english(city: str) -> dict:
    return {
        "reddit": [
            f"best breakfast in {city}",
            f"best brunch in {city}",
            f"best lunch in {city}",
            f"best dinner in {city}",
            f"best restaurants in {city}",
            f"where to eat in {city} locals",
            f"{city} coffee shops",
            f"{city} pastry shops",
            f"{city} tapas recommendations",
            f"{city} dessert spots",
        ],
        "tiktok": [
            f"{city} breakfast",
            f"{city} brunch",
            f"{city} lunch spots",
            f"{city} dinner spots",
            f"best restaurants in {city}",
            f"{city} coffee",
            f"{city} tapas",
            f"{city} desserts",
        ],
        "pinterest": [
            f"{city} breakfast guide",
            f"{city} brunch guide",
            f"{city} food guide",
            f"best restaurants in {city}",
            f"{city} cafes",
            f"{city} desserts",
        ],
    }


def _food_queries_spanish(city: str) -> dict:
    return {
        "reddit": [
            f"mejor desayuno en {city}",
            f"mejor brunch en {city}",
            f"mejor comida en {city}",
            f"mejor cena en {city}",
            f"mejores restaurantes en {city}",
            f"donde comer en {city}",
            f"cafeterias en {city}",
            f"pastelerias en {city}",
            f"tapas en {city} recomendaciones",
            f"postres en {city}",
        ],
        "tiktok": [
            f"desayuno en {city}",
            f"brunch en {city}",
            f"comida en {city}",
            f"cena en {city}",
            f"restaurantes en {city}",
            f"cafes en {city}",
            f"tapas en {city}",
            f"postres en {city}",
        ],
        "pinterest": [
            f"guia desayuno {city}",
            f"guia brunch {city}",
            f"guia comida {city}",
            f"restaurantes en {city}",
            f"cafeterias en {city}",
            f"postres en {city}",
        ],
    }


def _explore_queries_english(city: str) -> dict:
    return {
        "reddit": [
            f"{city} hidden gems",
            f"things to do {city} locals",
            f"{city} underrated activities",
        ],
        "tiktok": [
            f"{city} hidden gems",
            f"things to do {city}",
            f"{city} travel guide locals",
        ],
        "pinterest": [
            f"{city} travel guide",
            f"{city} things to do",
        ],
    }


def _explore_queries_spanish(city: str) -> dict:
    return {
        "reddit": [
            f"{city} qué ver",
            f"planes {city} recomendaciones",
            f"{city} sitios poco conocidos",
        ],
        "tiktok": [
            f"{city} qué hacer",
            f"{city} sitios bonitos",
            f"viajar {city}",
        ],
        "pinterest": [
            f"{city} qué ver",
            f"guía {city}",
        ],
    }


def build_search_queries(trip: TripParameters) -> dict:
    """Return platform specific query lists for the city, mode, and locale.

    Food queries are always included because every itinerary — even a full
    sightseeing one — needs real breakfast, lunch, snack, and dinner venues.
    """
    city = trip.city.strip()
    base = _food_queries_english(city)
    if should_include_spanish_queries(trip):
        base = _merge_query_dicts(base, _food_queries_spanish(city))

    if not trip.food_focused:
        base = _merge_query_dicts(base, _explore_queries_english(city))
        if should_include_spanish_queries(trip):
            base = _merge_query_dicts(base, _explore_queries_spanish(city))

    return base


def create_driver() -> webdriver.Chrome:
    """Create a Chrome driver with settings that reduce the chance of bot detection."""
    chrome_options = webdriver.ChromeOptions()
    if os.environ.get("HIDDENREC_HEADLESS", "").lower() in ("1", "true", "yes"):
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
    else:
        chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": (
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        },
    )
    return driver


def scroll_page(driver: webdriver.Chrome, times: int = 3) -> None:
    """Scroll incrementally to trigger lazy loaded content before scraping."""
    for _ in range(times):
        driver.execute_script(f"window.scrollBy(0, {SCROLL_DISTANCE_PX})")
        time.sleep(SCROLL_PAUSE_SECONDS)


def dismiss_cookie_banner(driver: webdriver.Chrome) -> None:
    """Click the first matching cookie acceptance button if one exists on the page."""
    for label in COOKIE_ACCEPT_LABELS:
        try:
            xpath = (
                "//button[contains("
                "translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
                f", '{label}')]"
            )
            driver.find_element(By.XPATH, xpath).click()
            time.sleep(1)
            return
        except Exception:
            continue


def find_elements_by_first_matching_selector(
    driver: webdriver.Chrome,
    selectors: list,
) -> list:
    """Return elements from the first selector that produces a non empty result."""
    for selector in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            return elements
    return []


def build_scraped_result(platform: str, text: str, url: str):
    """Return a ScrapedResult only when the text meets the minimum length requirement."""
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return None
    return ScrapedResult(platform=platform, text=text.strip(), url=url)


def scrape_reddit(driver: webdriver.Chrome, queries: list) -> list:
    """Scrape Reddit search results and return post titles and visible snippets."""
    results = []

    for query in queries:
        try:
            encoded_query = query.replace(" ", "+")
            url = (
                f"https://www.reddit.com/search/?q={encoded_query}&sort=top&t=year"
            )
            driver.get(url)
            time.sleep(PAGE_LOAD_SECONDS)
            dismiss_cookie_banner(driver)
            scroll_page(driver, times=3)

            posts = find_elements_by_first_matching_selector(driver, REDDIT_SELECTORS)
            for post in posts[:MAX_POSTS_PER_QUERY]:
                result = build_scraped_result("Reddit", post.text, driver.current_url)
                if result:
                    results.append(result)

            snippets = driver.find_elements(
                By.CSS_SELECTOR,
                "[data-testid='post-content'] p",
            )
            for snippet in snippets[:8]:
                result = build_scraped_result(
                    "Reddit", snippet.text, driver.current_url
                )
                if result:
                    results.append(result)

            print(f"Reddit '{query}': {len(posts)} posts collected.")
        except Exception as error:
            print(f"Reddit scrape failed for '{query}': {error}")

        time.sleep(POST_ACTION_PAUSE_SECONDS)

    return results


def scrape_tiktok(driver: webdriver.Chrome, queries: list) -> list:
    """Scrape TikTok video description text from search result pages."""
    results = []

    for query in queries:
        try:
            encoded_query = query.replace(" ", "%20")
            driver.get(f"https://www.tiktok.com/search?q={encoded_query}")
            time.sleep(TIKTOK_LOAD_SECONDS)
            dismiss_cookie_banner(driver)
            scroll_page(driver, times=4)

            items = find_elements_by_first_matching_selector(driver, TIKTOK_SELECTORS)
            for item in items[:MAX_POSTS_PER_QUERY]:
                result = build_scraped_result("TikTok", item.text, driver.current_url)
                if result:
                    results.append(result)

            print(f"TikTok '{query}': {len(items)} descriptions collected.")
        except Exception as error:
            print(f"TikTok scrape failed for '{query}': {error}")

        time.sleep(POST_ACTION_PAUSE_SECONDS + 1)

    return results


def scrape_pinterest(driver: webdriver.Chrome, queries: list) -> list:
    """Scrape Pinterest pin image alt text and titles."""
    results = []

    for query in queries:
        try:
            encoded_query = query.replace(" ", "%20")
            driver.get(f"https://www.pinterest.com/search/pins/?q={encoded_query}")
            time.sleep(PAGE_LOAD_SECONDS)
            dismiss_cookie_banner(driver)
            scroll_page(driver, times=4)

            images = driver.find_elements(By.CSS_SELECTOR, "img[alt]")
            for image in images[:20]:
                result = build_scraped_result(
                    "Pinterest",
                    image.get_attribute("alt"),
                    driver.current_url,
                )
                if result:
                    results.append(result)

            titles = driver.find_elements(
                By.CSS_SELECTOR,
                "[data-test-id='pinTitle'], h3, [class*='PinTitle']",
            )
            for title in titles[:15]:
                result = build_scraped_result(
                    "Pinterest",
                    title.text,
                    driver.current_url,
                )
                if result:
                    results.append(result)

            print(
                f"Pinterest '{query}': {len(images) + len(titles)} elements collected."
            )
        except Exception as error:
            print(f"Pinterest scrape failed for '{query}': {error}")

        time.sleep(POST_ACTION_PAUSE_SECONDS)

    return results


def run_all_scrapers(
    driver: webdriver.Chrome,
    trip: TripParameters,
    queries: dict,
) -> list:
    """Run all platform scrapers in sequence and return the combined results."""
    all_results = []
    all_results.extend(scrape_reddit(driver, queries["reddit"]))
    all_results.extend(scrape_tiktok(driver, queries["tiktok"]))
    all_results.extend(scrape_pinterest(driver, queries["pinterest"]))

    if trip.food_focused:
        all_results.sort(key=lambda r: _food_relevance_score(r.text), reverse=True)

    return all_results


def _is_tkinter_missing(exc: BaseException) -> bool:
    if isinstance(exc, ModuleNotFoundError):
        if getattr(exc, "name", None) in ("_tkinter", "tkinter"):
            return True
    text = str(exc).lower()
    return "_tkinter" in text or "tkinter" in text


def main() -> None:
    """Launch the HiddenRec desktop form, or the CLI if tkinter is unavailable."""
    try:
        from hiddenrec_ui import run_hiddenrec_app
    except ImportError as exc:
        if _is_tkinter_missing(exc):
            from hiddenrec_cli import run_cli_app

            run_cli_app()
            return
        raise
    run_hiddenrec_app()


if __name__ == "__main__":
    main()
