from dataclasses import dataclass, field
from datetime import datetime
import re
import os
import time
import webbrowser

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


MAX_POSTS_PER_QUERY = 12
MAX_PLACES_IN_OUTPUT = 25
MIN_PLACE_SCORE = 2
MIN_TEXT_LENGTH = 5
MIN_PLACE_NAME_LENGTH = 3
MAX_PLACE_NAME_LENGTH = 50
SNIPPET_STORAGE_MAX_LENGTH = 160
SNIPPET_DISPLAY_MAX_LENGTH = 130
SCROLL_DISTANCE_PX = 700
SCROLL_PAUSE_SECONDS = 1.5
PAGE_LOAD_SECONDS = 4
POST_ACTION_PAUSE_SECONDS = 2
TIKTOK_LOAD_SECONDS = 5
INSTAGRAM_LOGIN_SECONDS = 6
TRIGGER_WORD_SCORE = 3
PROPER_NOUN_SCORE = 1

TRIGGER_WORDS = [
    "go to", "try", "visit", "eat at", "check out", "stop by",
    "must visit", "recommend", "love", "favorite", "favourite",
    "best", "amazing", "hidden gem", "underrated",
]

NOISE_WORDS = frozenset({
    "the", "a", "an", "is", "it", "this", "that", "there", "here",
    "was", "are", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "from", "just", "so", "very", "really", "also",
    "we", "i", "you", "he", "she", "they", "my", "your", "our",
    "its", "been", "have", "has", "had", "if", "when", "where",
    "what", "how", "why", "which", "who", "one", "two", "like",
    "not", "no", "yes", "all", "some", "any", "more", "than",
    "then", "their", "them", "these", "those", "would", "could",
    "should", "will", "can", "do", "did", "be", "am", "as", "up",
    "out", "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "each", "every", "both", "few",
    "other", "same", "too", "while", "by", "him", "her",
    "city", "place", "spot", "area", "street", "road", "avenue",
    "people", "time", "way", "day", "night", "year", "thing",
    "super", "great", "good", "nice", "cool", "awesome",
})

PLATFORM_COLORS = {
    "Reddit": "#FF4500",
    "TikTok": "#69C9D0",
    "Pinterest": "#E60023",
    "Instagram": "#C13584",
}

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

# Instagram DOM changes often; try several patterns for post preview images with alt text.
INSTAGRAM_IMAGE_SELECTORS = [
    "article img[alt]",
    "main article img[alt]",
    "ul li img[alt]",
    "div[style*='flex'] img[alt]",
    "img[alt][draggable='false']",
]


@dataclass
class Config:
    city: str
    food_mode: bool
    instagram_login: bool
    instagram_username: str = ""
    instagram_password: str = ""


@dataclass
class ScrapedResult:
    platform: str
    text: str
    url: str


@dataclass
class PlaceData:
    score: int = 0
    platforms: set = field(default_factory=set)
    snippets: list = field(default_factory=list)
    urls: list = field(default_factory=list)


def get_user_config() -> Config:
    """Collect and validate all user inputs before any browser activity starts."""
    city = input("City to explore: ").strip()
    if not city:
        raise ValueError("City name cannot be empty.")

    food_mode = input("Food-only mode? (y/n): ").strip().lower() == "y"
    instagram_login = input("Log in to Instagram? (y/n): ").strip().lower() == "y"

    instagram_username = ""
    instagram_password = ""
    if instagram_login:
        instagram_username = input("  Instagram username: ").strip()
        instagram_password = input("  Instagram password: ").strip()
        if not instagram_username or not instagram_password:
            raise ValueError("Instagram credentials cannot be empty when login is enabled.")

    return Config(
        city=city,
        food_mode=food_mode,
        instagram_login=instagram_login,
        instagram_username=instagram_username,
        instagram_password=instagram_password,
    )


def build_search_queries(config: Config) -> dict:
    """Return platform-specific query lists tailored to the selected city and mode."""
    city = config.city
    city_slug = city.lower().replace(" ", "")

    if config.food_mode:
        return {
            "reddit": [
                f"{city} best restaurants",
                f"{city} food hidden gems",
                f"where to eat {city} locals",
            ],
            "tiktok": [
                f"{city} food",
                f"best food {city}",
                f"{city} restaurant local",
            ],
            "pinterest": [
                f"{city} food guide",
                f"best eats {city}",
            ],
            "instagram_hashtags": [
                f"{city_slug}food",
                f"{city_slug}eats",
                f"foodie{city_slug}",
            ],
        }

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
        "instagram_hashtags": [
            f"{city_slug}travel",
            f"visit{city_slug}",
            f"{city_slug}hidden",
        ],
    }


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
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def scroll_page(driver: webdriver.Chrome, times: int = 3) -> None:
    """Scroll incrementally to trigger lazy-loaded content before scraping."""
    for _ in range(times):
        driver.execute_script(f"window.scrollBy(0, {SCROLL_DISTANCE_PX})")
        time.sleep(SCROLL_PAUSE_SECONDS)


def dismiss_cookie_banner(driver: webdriver.Chrome) -> None:
    """Click the first matching cookie acceptance button if one exists on the page."""
    for label in COOKIE_ACCEPT_LABELS:
        try:
            xpath = (
                f"//button[contains("
                f"translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
                f", '{label}')]"
            )
            driver.find_element(By.XPATH, xpath).click()
            time.sleep(1)
            return
        except Exception:
            continue


def find_elements_by_first_matching_selector(
    driver: webdriver.Chrome, selectors: list
) -> list:
    """Return elements from the first selector that produces a non-empty result."""
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
            driver.get(f"https://www.reddit.com/search/?q={encoded_query}&sort=top&t=year")
            time.sleep(PAGE_LOAD_SECONDS)
            dismiss_cookie_banner(driver)
            scroll_page(driver, times=3)

            posts = find_elements_by_first_matching_selector(driver, REDDIT_SELECTORS)
            for post in posts[:MAX_POSTS_PER_QUERY]:
                result = build_scraped_result("Reddit", post.text, driver.current_url)
                if result:
                    results.append(result)

            snippets = driver.find_elements(By.CSS_SELECTOR, "[data-testid='post-content'] p")
            for snippet in snippets[:8]:
                result = build_scraped_result("Reddit", snippet.text, driver.current_url)
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
    """Scrape Pinterest pin image alt text and titles, which are rich in location detail."""
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
                    "Pinterest", image.get_attribute("alt"), driver.current_url
                )
                if result:
                    results.append(result)

            titles = driver.find_elements(
                By.CSS_SELECTOR, "[data-test-id='pinTitle'], h3, [class*='PinTitle']"
            )
            for title in titles[:15]:
                result = build_scraped_result("Pinterest", title.text, driver.current_url)
                if result:
                    results.append(result)

            print(f"Pinterest '{query}': {len(images) + len(titles)} elements collected.")
        except Exception as error:
            print(f"Pinterest scrape failed for '{query}': {error}")

        time.sleep(POST_ACTION_PAUSE_SECONDS)

    return results


def login_to_instagram(driver: webdriver.Chrome, username: str, password: str) -> bool:
    """Attempt to log in to Instagram and dismiss post-login prompts. Returns True on success."""
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        dismiss_cookie_banner(driver)

        wait = WebDriverWait(driver, 15)
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        username_field.clear()
        username_field.send_keys(username)

        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys(password)
        password_field.send_keys(Keys.ENTER)
        time.sleep(INSTAGRAM_LOGIN_SECONDS)

        for xpath in ["//button[text()='Not Now']", "//button[contains(.,'Not now')]"]:
            try:
                driver.find_element(By.XPATH, xpath).click()
                time.sleep(2)
                break
            except Exception:
                continue

        print("Instagram login succeeded.")
        return True
    except Exception as error:
        print(f"Instagram login failed: {error}. Continuing without it.")
        return False


def scrape_instagram(driver: webdriver.Chrome, config: Config, hashtags: list) -> list:
    """Scrape Instagram hashtag pages for post image descriptions."""
    results = []

    if config.instagram_login:
        login_succeeded = login_to_instagram(
            driver, config.instagram_username, config.instagram_password
        )
        if not login_succeeded:
            return results

    for hashtag in hashtags:
        try:
            driver.get(f"https://www.instagram.com/explore/tags/{hashtag}/")
            time.sleep(PAGE_LOAD_SECONDS)
            dismiss_cookie_banner(driver)
            scroll_page(driver, times=3)

            images = find_elements_by_first_matching_selector(
                driver, INSTAGRAM_IMAGE_SELECTORS
            )
            if not images:
                images = driver.find_elements(By.CSS_SELECTOR, "img[alt]")
            for image in images[:15]:
                result = build_scraped_result(
                    "Instagram", image.get_attribute("alt"), driver.current_url
                )
                if result:
                    results.append(result)

            print(f"Instagram #{hashtag}: {len(images)} posts collected.")
        except Exception as error:
            print(f"Instagram scrape failed for #{hashtag}: {error}")

        time.sleep(3)

    return results


def run_all_scrapers(driver: webdriver.Chrome, config: Config, queries: dict) -> list:
    """Run all platform scrapers in sequence and return the combined results."""
    all_results = []
    all_results.extend(scrape_reddit(driver, queries["reddit"]))
    all_results.extend(scrape_tiktok(driver, queries["tiktok"]))
    all_results.extend(scrape_pinterest(driver, queries["pinterest"]))

    # Hashtag pages work without login (may show a login wall in some regions); login is optional.
    all_results.extend(scrape_instagram(driver, config, queries["instagram_hashtags"]))

    return all_results


class PlaceExtractor:
    """
    Extracts and scores likely place names from raw scraped text.

    Two heuristics work together: phrases that follow known recommendation
    trigger words score higher, while capitalized proper noun clusters score
    lower but still contribute. Places mentioned across multiple platforms or
    many posts naturally accumulate a higher score and rise to the top.
    """

    def __init__(self):
        self.place_data: dict = {}

    def process_result(self, result: ScrapedResult) -> None:
        """Extract place candidates from a result and update their scores."""
        self._extract_by_trigger_words(result)
        self._extract_by_proper_nouns(result)

    def get_ranked_places(self) -> list:
        """Return place entries sorted by score, filtered to those above the minimum threshold."""
        qualified = [
            (name, data)
            for name, data in self.place_data.items()
            if data.score >= MIN_PLACE_SCORE and self._is_valid_place_name(name)
        ]
        return sorted(
            qualified,
            key=lambda item: (item[1].score, len(item[1].platforms)),
            reverse=True,
        )[:MAX_PLACES_IN_OUTPUT]

    def _extract_by_trigger_words(self, result: ScrapedResult) -> None:
        """Find place names that appear directly after a recommendation trigger phrase."""
        for trigger in TRIGGER_WORDS:
            pattern = (
                rf'(?i)\b{re.escape(trigger)}\b\s+'
                rf'([A-Z][^\.\!\?\n]{{2,{MAX_PLACE_NAME_LENGTH}}}?)(?=[,\.\!\?\n]|$)'
            )
            for match in re.findall(pattern, result.text):
                name = self._clean_name(match)
                if self._is_valid_place_name(name):
                    self._record_place(name, result, TRIGGER_WORD_SCORE)

    def _extract_by_proper_nouns(self, result: ScrapedResult) -> None:
        """Find capitalized multi-word sequences that likely represent named locations."""
        pattern = r'\b([A-Z][a-záéíóúñü]+(?:\s+[A-Z][a-záéíóúñü]+)+)\b'
        for match in re.findall(pattern, result.text):
            name = self._clean_name(match)
            if self._is_valid_place_name(name):
                self._record_place(name, result, PROPER_NOUN_SCORE)

    def _record_place(self, name: str, result: ScrapedResult, points: int) -> None:
        """Add score and metadata to a place entry, creating it if it does not yet exist."""
        if name not in self.place_data:
            self.place_data[name] = PlaceData()

        entry = self.place_data[name]
        entry.score += points
        entry.platforms.add(result.platform)

        snippet = result.text[:SNIPPET_STORAGE_MAX_LENGTH].strip()
        if snippet not in entry.snippets:
            entry.snippets.append(snippet)

        if result.url and result.url not in entry.urls:
            entry.urls.append(result.url)

    @staticmethod
    def _clean_name(raw: str) -> str:
        """Strip surrounding punctuation and collapse internal whitespace."""
        return re.sub(r"\s+", " ", raw.strip(" .,!?\"'"))

    @staticmethod
    def _is_valid_place_name(name: str) -> bool:
        """Return False if the name is outside acceptable length or made entirely of noise words."""
        if not (MIN_PLACE_NAME_LENGTH < len(name) < MAX_PLACE_NAME_LENGTH):
            return False
        return not all(word in NOISE_WORDS for word in name.lower().split())


def build_place_cards_html(ranked_places: list, top_score: int) -> str:
    """Render the HTML card elements for every ranked place."""
    if not ranked_places:
        return (
            '<article class="card">'
            "<h2>No specific places found.</h2>"
            '<p class="snippet">Try a larger city or switch modes. '
            "The bot collected posts but could not extract distinct place names.</p>"
            "</article>"
        )

    rank_labels = ["1st", "2nd", "3rd"]
    cards = []

    for index, (name, data) in enumerate(ranked_places):
        badges_html = "".join(
            f'<span class="badge" style="--badge-color:{PLATFORM_COLORS.get(p, "#888")}">'
            f"{p}</span>"
            for p in sorted(data.platforms)
        )
        snippet = (data.snippets[0][:SNIPPET_DISPLAY_MAX_LENGTH] + "...") if data.snippets else ""
        source_url = data.urls[0] if data.urls else "#"
        rank_label = rank_labels[index] if index < 3 else f"#{index + 1}"
        heat_percent = min(100, int(data.score / max(1, top_score) * 100))
        animation_delay_ms = index * 60

        cards.append(f"""
    <article class="card" style="--delay:{animation_delay_ms}ms"
             onclick="window.open('{source_url}', '_blank')">
      <div class="card-top">
        <span class="rank-label">{rank_label}</span>
        <div class="heat-track">
          <div class="heat-fill" style="--heat:{heat_percent}%"></div>
        </div>
      </div>
      <h2 class="place-name">{name}</h2>
      <p class="snippet">{snippet}</p>
      <footer class="card-footer">
        <div class="badges">{badges_html}</div>
        <span class="signal-count">{data.score} signals</span>
      </footer>
    </article>""")

    return "\n".join(cards)


def generate_html_page(config: Config, all_results: list, ranked_places: list) -> str:
    """Render the complete HTML output page as a string."""
    mode_label = "Food Guide" if config.food_mode else "Explorer Mode"
    platform_names = ", ".join(sorted(set(result.platform for result in all_results)))
    top_score = ranked_places[0][1].score if ranked_places else 1
    cards_html = build_place_cards_html(ranked_places, top_score)
    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")
    total_posts = len(all_results)
    total_platforms = len(set(result.platform for result in all_results))
    total_places = len(ranked_places)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LocalLens: {config.city}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:ital,wght@0,300;0,400;1,300&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #080808;
  --surface: #111;
  --border: #1e1e1e;
  --text: #e8e8e8;
  --muted: #555;
  --accent: #f0e040;
  --radius: 14px;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'DM Sans', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}}

body::before {{
  content: '';
  position: fixed; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none; z-index: 0; opacity: 0.35;
}}

.hero {{
  position: relative; z-index: 1;
  padding: 80px 40px 60px;
  max-width: 1300px; margin: 0 auto;
  display: flex; flex-direction: column; gap: 20px;
}}

.mode-pill {{
  display: inline-flex; align-items: center;
  background: #ffffff0d; border: 1px solid #ffffff18;
  border-radius: 999px; padding: 5px 16px;
  font-size: 0.75rem; font-weight: 400;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--muted); width: fit-content;
}}

.hero h1 {{
  font-family: 'Syne', sans-serif;
  font-size: clamp(3.5rem, 10vw, 8rem);
  font-weight: 800; line-height: 0.95;
  letter-spacing: -0.04em;
}}

.city-accent {{ color: var(--accent); display: block; }}

.tagline {{
  font-size: 1rem; color: var(--muted);
  font-weight: 300; max-width: 480px; line-height: 1.6;
}}

.stats-row {{
  display: flex;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  margin-bottom: 60px;
}}

.stat {{
  flex: 1; padding: 28px 40px;
  border-right: 1px solid var(--border);
}}

.stat:last-child {{ border-right: none; }}

.stat-number {{
  font-family: 'Syne', sans-serif;
  font-size: 2.6rem; font-weight: 800;
  line-height: 1; margin-bottom: 4px;
}}

.stat-label {{
  font-size: 0.7rem; color: var(--muted);
  letter-spacing: 0.12em; text-transform: uppercase;
}}

.grid-section {{
  max-width: 1300px; margin: 0 auto;
  padding: 0 40px 80px; position: relative; z-index: 1;
}}

.section-label {{
  font-size: 0.7rem; color: var(--muted);
  letter-spacing: 0.15em; text-transform: uppercase;
  margin-bottom: 24px;
}}

.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}}

.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px; cursor: pointer;
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
  animation: rise 0.5s var(--delay, 0ms) both;
}}

.card:hover {{
  border-color: #ffffff22;
  transform: translateY(-3px);
  box-shadow: 0 12px 40px #00000080;
}}

.card-top {{
  display: flex; align-items: center;
  gap: 14px; margin-bottom: 16px;
}}

.rank-label {{
  font-family: 'Syne', sans-serif;
  font-size: 0.85rem; font-weight: 700;
  color: var(--muted); flex-shrink: 0;
}}

.heat-track {{
  flex: 1; height: 3px;
  background: #ffffff0a; border-radius: 2px; overflow: hidden;
}}

.heat-fill {{
  height: 100%; width: var(--heat, 0%);
  background: linear-gradient(90deg, var(--accent), #f08040);
  border-radius: 2px;
}}

.place-name {{
  font-family: 'Syne', sans-serif;
  font-size: 1.15rem; font-weight: 700;
  line-height: 1.25; margin-bottom: 10px;
}}

.snippet {{
  font-size: 0.82rem; color: var(--muted);
  line-height: 1.55; font-style: italic; margin-bottom: 18px;
  display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden;
}}

.card-footer {{
  display: flex; align-items: center;
  justify-content: space-between; gap: 8px;
}}

.badges {{ display: flex; flex-wrap: wrap; gap: 5px; }}

.badge {{
  font-size: 0.65rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 9px; border-radius: 999px;
  background: var(--badge-color, #888); color: #fff; opacity: 0.9;
}}

.signal-count {{
  font-size: 0.7rem; color: var(--muted);
  white-space: nowrap; font-weight: 300;
}}

.page-footer {{
  position: relative; z-index: 1;
  border-top: 1px solid var(--border);
  padding: 24px 40px; max-width: 1300px; margin: 0 auto;
  display: flex; justify-content: space-between;
  font-size: 0.75rem; color: var(--muted);
}}

@keyframes rise {{
  from {{ opacity: 0; transform: translateY(18px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

@media (max-width: 700px) {{
  .hero {{ padding: 50px 20px 40px; }}
  .stats-row {{ flex-direction: column; }}
  .stat {{ border-right: none; border-bottom: 1px solid var(--border); padding: 20px; }}
  .grid-section {{ padding: 0 20px 60px; }}
  .page-footer {{ flex-direction: column; gap: 6px; text-align: center; }}
}}
</style>
</head>
<body>

<section class="hero">
  <div class="mode-pill">{mode_label}</div>
  <h1>
    {config.city}
    <span class="city-accent">by locals.</span>
  </h1>
  <p class="tagline">
    Not Google. Not sponsored listicles.
    What real people on {platform_names} actually visit.
  </p>
</section>

<div class="stats-row">
  <div class="stat">
    <div class="stat-number">{total_posts}</div>
    <div class="stat-label">Posts Scraped</div>
  </div>
  <div class="stat">
    <div class="stat-number">{total_platforms}</div>
    <div class="stat-label">Platforms</div>
  </div>
  <div class="stat">
    <div class="stat-number">{total_places}</div>
    <div class="stat-label">Places Ranked</div>
  </div>
  <div class="stat">
    <div class="stat-number">0</div>
    <div class="stat-label">Sponsored Results</div>
  </div>
</div>

<div class="grid-section">
  <p class="section-label">
    Ranked by local signal strength. Click any card to view the source.
  </p>
  <div class="grid">
    {cards_html}
  </div>
</div>

<footer class="page-footer">
  <span>LocalLens, generated on {generated_at}.</span>
  <span>Sources: {platform_names}.</span>
</footer>

</body>
</html>"""


def save_and_open_html(html_content: str, city: str) -> str:
    """Write the rendered HTML to the user's home directory and open it in the browser."""
    timestamp = datetime.now().strftime("%H%M")
    filename = f"locallens_{city.replace(' ', '_').lower()}_{timestamp}.html"
    output_path = os.path.join(os.path.expanduser("~"), filename)

    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(html_content)

    print(f"Output saved to {output_path}.")
    webbrowser.open(f"file://{output_path}")
    return output_path


def main() -> None:
    config = get_user_config()
    queries = build_search_queries(config)
    driver = create_driver()

    try:
        all_results = run_all_scrapers(driver, config, queries)

        extractor = PlaceExtractor()
        for result in all_results:
            extractor.process_result(result)

        ranked_places = extractor.get_ranked_places()
        print(f"Processed {len(all_results)} posts. Found {len(ranked_places)} ranked places.")

        html_content = generate_html_page(config, all_results, ranked_places)
        save_and_open_html(html_content, config.city)

    finally:
        input("Press Enter to close the browser and exit.")
        driver.quit()


if __name__ == "__main__":
    main()