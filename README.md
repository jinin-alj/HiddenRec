# HiddenRec

HiddenRec turns trip ideas from real social posts into a calendar file you can open in minutes. It is meant for people who like travel planning in theory but not the late night tab overload that so often comes with it.

## Why use a bot for your itinerary

Planning a trip can be genuinely enjoyable, and then it can quietly become work. You end up with too many browser tabs, half remembered videos that you cannot quite place, vague plans about eating somewhere nice for lunch, and a notes file that never quite turns into a schedule. HiddenRec is built to take on that consolidation step. It collects what people are posting about your destination, then asks a language model to organize those signals into a structured day by day plan with breakfast, activities, lunch, snacks, and dinner in timed slots. The ideas are steered toward the season implied by your dates, toward a total budget and currency you provide, and toward the city and country you name so the plan stays geographically sensible. You receive an ICS file that imports cleanly into Apple Calendar, Google Calendar, or Outlook. You do not create an account with HiddenRec itself. You simply supply city, country, dates, budget, timezone, and how you want search language handled, then run the app.

The pitch is simple enough. You can spend more of your attention on the trip itself instead of re opening the same Pinterest board at one in the morning.

## What the project actually does

HiddenRec is a small desktop application, and there is a command line path when you prefer scripts or when a graphical toolkit is missing from your Python build.

The application searches Reddit, TikTok, and Pinterest for your city. The query lists include meal focused searches such as breakfast and lunch and dinner, alongside sightseeing style queries, and when your destination or locale settings suggest it, the same ideas are also expressed in Spanish so local language posts are more likely to surface.

The scraped text is sent to a large language model with instructions to output strict JSON. By default the model runs locally through Ollama and its OpenAI compatible API. If you configure an OpenAI API key and the backend selection allows it, you can use OpenAI hosted models instead.

The pipeline then validates and normalizes the plan so each day has consistent time blocks, then writes a file under the exports folder beside this repository. The filename follows a simple pattern that includes the city and start date so runs are easy to tell apart.

Instagram is deliberately not part of the stack because login friction and noisy results make it a weak default for this workflow. If you extend HiddenRec, reasonable next steps include official places APIs or similarly structured sources for hours and addresses.

## Features in plain terms

City and country work together as fixed anchors. You must enter a country in the graphical form and on the command line so the scraper and the model both know which part of the world you mean, which reduces the chance that the itinerary drifts to the wrong place.

Season comes from your trip start date. The planner derives a season label such as spring or winter and uses it to favor activities that fit that time of year and to avoid suggestions that clash with the weather you are likely to have.

Budget and currency are yours to set. The model is asked to respect the total amount you give, and the plan can include short notes when estimated spend might exceed what you wanted.

Search language or locale controls how query strings are built for scraping. That matters because switching toward local language queries can surface recommendations that English only search might miss.

Food only mode exists for trips where you only want meal slots such as breakfast, lunch, a snack, and dinner, without mixing in general sightseeing blocks.

Full itinerary mode is the default and gives you seven blocks per day in a fixed order, breakfast then activities and lunch and more activities and a snack and dinner, with stable local times in the exported calendar.

Timezone uses a standard IANA name so event times in the ICS file match local time at the destination. A common choice for Spain is the zone called Europe slash Madrid in the standard registry.

The model is instructed to take real venue names from the scraped post text when it can, instead of inventing generic titles that only repeat the city name.

The default stack is friendly to privacy minded use because Ollama runs on your machine and no cloud language model is required unless you opt in.

## How a typical run feels

You start HiddenRec with python hiddenrec.py when you want the graphical form. You enter city, country, start date, number of days, budget, currency, timezone, and search language. If you only care about food, you enable food only mode. You press the button to begin. Chrome opens unless you have forced headless mode, and the app runs curated searches on each platform in turn. You see progress while posts are gathered and while the language model produces and repairs a JSON itinerary. When the run completes, the interface shows where the ICS file was saved, usually under exports next to the code.

If you prefer the terminal or you are on a Python build without Tkinter, you can run python hiddenrec_cli.py with the same trip parameters. Passing arguments to hiddenrec.py only enters the command line flow when the graphical import fails for lack of Tkinter, so for normal desktop use the CLI module is the reliable way to script a run.

## Where the calendar file goes

Files land in the exports directory next to the project. A typical path looks like the HiddenRec folder, then exports, then a file whose name starts with hiddenrec, includes the city and start date, and ends in ics. The graphical interface prints the full path when processing finishes.

## Getting started

You need Python 3 and Google Chrome because Selenium drives Chrome for scraping. For the default local model path you also need Ollama installed and at least one model pulled, for example llama3.1 8b.

Create a virtual environment, install requirements, and launch the graphical app.

```bash
cd /path/to/HiddenRec
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python hiddenrec.py
```

On Windows you would activate with .venv\Scripts\activate instead of the source line above.

Keep the Ollama application or service running. Confirm your model appears when you run ollama list.

For command line use:

```bash
python hiddenrec_cli.py --city Madrid --country Spain --start 2026-06-15 --days 3
```

Additional flags cover budget, currency, food focused mode, timezone, and locale. To see every option, run python hiddenrec_cli.py --help in your terminal.

Set the environment variable HIDDENREC_HEADLESS to 1 or true or yes if you need Chrome to run without a visible window, which is sometimes useful on servers. Pillow is optional and only affects logo rendering in the graphical interface.

## Choosing Ollama or OpenAI

Ollama exposes an OpenAI compatible base URL, typically [http://127.0.0.1:11434/v1](http://127.0.0.1:11434/v1), and HiddenRec uses the openai Python package purely as an HTTP client toward that endpoint. No OpenAI account is needed for that path.

If you set OPENAI_API_KEY in your environment and you do not force the backend to Ollama with HIDDENREC_LLM_BACKEND, the app can call OpenAI instead. The section that follows walks through each related environment variable in order.

## Environment variables

These are optional unless you need non default behavior.

OPENAI_API_KEY selects cloud OpenAI when set and when the backend logic allows it.

HIDDENREC_LLM_BACKEND can be openai or ollama and overrides automatic selection.

HIDDENREC_LLM_MODEL sets the model name for OpenAI, with a default of gpt-4o-mini, or acts as a fallback name when the Ollama specific variable is unset.

HIDDENREC_OLLAMA_MODEL is the Ollama tag, defaulting to llama3.1 8b.

HIDDENREC_OLLAMA_BASE_URL is the OpenAI compatible base, defaulting to [http://127.0.0.1:11434/v1](http://127.0.0.1:11434/v1).

HIDDENREC_LLM_TIMEOUT_SECONDS caps how long one model call may wait, default 300 seconds.

HIDDENREC_OLLAMA_MAX_CORPUS_CHARS limits how much scraped text is sent when using Ollama, default twelve thousand characters, and you can raise it if your machine tolerates larger prompts.

HIDDENREC_HEADLESS controls headless Chrome as described earlier.

Example:

```bash
export HIDDENREC_OLLAMA_MODEL=llama3.1:8b
python hiddenrec_cli.py --city Lisbon --country Portugal --start 2026-06-15 --days 2
```

## Dependencies

Everything is listed in requirements.txt, including Selenium, webdriver manager, the OpenAI client, Pydantic, python dotenv, and httpx. Install with pip install -r requirements.txt inside your activated virtual environment.