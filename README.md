# Hotel Finder

A small Python web-chat demo that gathers a destination, dates, guest count, and optional nightly budget, then suggests matching sample hotels. When configured with a Google Gemini API key, it uses Gemini to interpret conversational requests and follow-up messages; Python still validates the extracted details and performs the hotel matching.

**This is a prototype, not a booking service.** Listings are fixture data only; availability and prices are not live, and the app cannot make reservations. Real booking functionality would require an authorized hotel-search/booking provider and its API credentials.

## Run locally

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For conversational interpretation, create a private `.env` file from the template:

```bash
cp .env.example .env
```

Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey). Open `.env` and replace `put-your-key-here` with that key. Do not share the key or commit `.env`; it is excluded by `.gitignore`. Then start the app:

```bash
uvicorn app:app --reload
```

Then open <http://127.0.0.1:8000> and try:

> Somewhere in Paris next weekend for me and my partner, ideally under $250 a night

The default model is `gemini-3.5-flash`; change `GEMINI_MODEL` in `.env` to another Gemini model available to your account. Environment variables set in your shell take precedence over `.env`.

If Gemini is temporarily overloaded, the chat will explain that it is busy and offer a **Try again** button rather than showing a generic server error.

If you do not have a key yet, leave `.env` absent and run `uvicorn app:app --reload`; the app will use the limited local parser instead.

Keep API keys private; do not put them in source code or commit them. When no Gemini key is configured, the app remains usable with its limited local parser (listed city names and `YYYY-MM-DD` dates) and tells you that AI interpretation is off.

Only the user's message, current search criteria, and current date are sent to Google Gemini for interpretation. Hotel matching still uses the sample records in `hotels.py`; this does not provide live inventory, prices, or booking.

## Tests

```bash
python -m unittest discover -s tests
```

## Render deployment preparation

`render.yaml` configures a free Render web service and its `/healthz` health check. The staging source is in the private [`demekcoe/stayfinder` GitHub repository](https://github.com/demekcoe/stayfinder). To deploy, sign in to Render, create a new Blueprint from that private repository, and authorize Render to access it if prompted. Enter your Gemini key for `GEMINI_API_KEY` when Render prompts for the secret; never commit or paste the key into GitHub. Render will build the Python dependencies and start the FastAPI server. Free web services may sleep when idle and take a little time to wake.

**This configuration does not connect Booking.com.** The current search still uses sample listings, so do not launch it as a real hotel-search service yet. Review the [Booking.com Demand API overview](https://developers.booking.com/demand/docs/getting-started/overview), apply for the appropriate partner access, and confirm which accommodation capabilities are approved for your account. Once approved, the integration needs to be implemented and tested against your credentials before real search can go live. No credentials should be pasted into chat or committed to this repository.
