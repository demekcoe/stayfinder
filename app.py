import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

from hotels import HOTELS, search_hotels


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Hotel Finder")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class Criteria(BaseModel):
    destination: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    guests: int | None = Field(default=None, ge=1, le=20)
    max_price: int | None = Field(default=None, ge=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    criteria: Criteria = Field(default_factory=Criteria)


class ChatResponse(BaseModel):
    reply: str
    criteria: Criteria
    hotels: list[dict[str, Any]] = Field(default_factory=list)


class Interpretation(BaseModel):
    criteria: Criteria
    clarification: str | None = None


@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/healthz")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/destinations")
def destinations() -> list[str]:
    return sorted({hotel["city"] for hotel in HOTELS})


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if (os.getenv("GEMINI_API_KEY") or "").strip() not in (
        "",
        "put-your-key-here",
    ):
        try:
            interpretation = interpret_with_gemini(request.message, request.criteria)
        except ValidationError as error:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned search details that could not be validated. Please try rephrasing.",
            ) from error
        criteria = interpretation.criteria
        clarification = interpretation.clarification
        parse_note = ""
    else:
        criteria, parse_note = update_criteria(request.message, request.criteria)
        parse_note = (
            "AI interpretation is not enabled because GEMINI_API_KEY is not set. "
            "I can currently recognize listed city names and YYYY-MM-DD dates. "
            + parse_note
        )
        clarification = None

    if criteria.check_in and criteria.check_out and criteria.check_out <= criteria.check_in:
        criteria.check_in = None
        criteria.check_out = None
        return ChatResponse(
            reply="Your check-out date must be after check-in. What dates would you like? Use YYYY-MM-DD.",
            criteria=criteria,
        )

    if clarification:
        return ChatResponse(reply=clarification, criteria=criteria)

    missing = [
        name
        for name, value in (
            ("destination", criteria.destination),
            ("check-in and check-out dates", criteria.check_in and criteria.check_out),
            ("number of guests", criteria.guests),
        )
        if not value
    ]
    if missing:
        return ChatResponse(
            reply=f"{parse_note}I still need your {', '.join(missing)}. "
            "You can share them together, for example: Paris, 2026-11-05 to 2026-11-08, 2 guests.",
            criteria=criteria,
        )

    results = search_hotels(criteria)
    if not results:
        return ChatResponse(
            reply=f"{parse_note}I couldn't find sample listings matching those preferences. "
            "Try another destination or a higher nightly budget.",
            criteria=criteria,
        )

    date_summary = f"{criteria.check_in:%b %d}–{criteria.check_out:%b %d}"
    budget_summary = (
        f", up to ${criteria.max_price}/night" if criteria.max_price else ""
    )
    return ChatResponse(
        reply=f"{parse_note}Here are sample stays in {criteria.destination} for "
        f"{criteria.guests} guest(s), {date_summary}{budget_summary}. "
        "These are demo listings, not live availability or bookable offers.",
        criteria=criteria,
        hotels=results,
    )


def interpret_with_gemini(message: str, current: Criteria) -> Interpretation:
    from google import genai
    from google.genai.errors import APIError
    from google.genai._gaos.lib.compat_errors import APIError as InteractionsAPIError

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    prompt = (
        "You extract hotel-search details from conversational English. "
        "Return criteria and, only if a required detail is genuinely ambiguous, "
        "one concise clarification question. Use null for unknown values and "
        "YYYY-MM-DD for dates. Update supplied criteria using this message, "
        "preserving prior details unless the user changes them. Never invent "
        "a destination, dates, guest count, or budget. Resolve relative dates "
        "using the provided current date. Treat max_price as a nightly USD "
        "budget only when the user gives a currency or context makes USD clear; "
        "do not guess a currency.\n\n"
        + json.dumps(
            {
                "current_date": date.today().isoformat(),
                "current_criteria": current.model_dump(mode="json"),
                "message": message,
            }
        )
    )
    try:
        response = client.interactions.create(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            input=prompt,
            store=False,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": Interpretation.model_json_schema(),
            },
        )
    except (APIError, InteractionsAPIError) as error:
        error_code = getattr(error, "code", None) or getattr(error, "status_code", None)
        error_message = getattr(error, "message", str(error))
        error_body = getattr(error, "body", None)
        if isinstance(error_body, dict):
            nested_error = error_body.get("error")
            if isinstance(nested_error, dict):
                error_code = error_code or nested_error.get("code")
                error_message = nested_error.get("message", error_message)
        if error_code in (401, 403):
            detail = (
                "Google rejected the Gemini API key. Check GEMINI_API_KEY in your "
                ".env file and restart the app."
            )
        elif error_code == 429:
            detail = (
                "The Gemini API rate limit or quota was reached. Check your Google AI "
                "Studio usage and billing, then try again."
            )
        elif error_code == 503 or error_code == "service_unavailable":
            detail = (
                "Gemini is temporarily busy due to high demand. Please wait a moment "
                "and try sending your message again."
            )
        elif error_code is None:
            detail = "Could not connect to Google Gemini. Check your internet connection and try again."
        else:
            detail = (
                f"Gemini could not process the request (HTTP {error_code}). "
                f"{error_message} "
                "Check the API account and selected model, then try again."
            )
        raise HTTPException(
            status_code=502,
            detail=detail,
        ) from error

    content = response.output_text
    if not content:
        raise HTTPException(
            status_code=502,
            detail="Gemini returned an empty response. Please try again.",
        )
    return Interpretation.model_validate_json(content)


def update_criteria(message: str, current: Criteria) -> tuple[Criteria, str]:
    updated = current.model_copy()
    text = message.strip()
    lowered = text.casefold()

    city = next(
        (hotel_city for hotel_city in sorted(
            {hotel["city"] for hotel in HOTELS}, key=len, reverse=True
        ) if hotel_city.casefold() in lowered),
        None,
    )
    if city:
        updated.destination = city

    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if len(dates) >= 2:
        try:
            updated.check_in = date.fromisoformat(dates[0])
            updated.check_out = date.fromisoformat(dates[1])
        except ValueError:
            return updated, "I couldn't read those dates. "
    elif len(dates) == 1:
        try:
            parsed_date = date.fromisoformat(dates[0])
        except ValueError:
            return updated, "I couldn't read that date. "
        if updated.check_in is None or updated.check_out is not None:
            updated.check_in = parsed_date
            updated.check_out = None
        else:
            updated.check_out = parsed_date

    guest_match = re.search(
        r"\b(\d{1,2})\s*(?:guest(?:s)?|people|person|adult(?:s)?|travelers?)\b"
        r"|\bfor\s+(\d{1,2})\b",
        lowered,
    )
    if guest_match:
        guests = int(guest_match.group(1) or guest_match.group(2))
        if 1 <= guests <= 20:
            updated.guests = guests

    budget_match = re.search(
        r"\b(?:under|below|up to|max(?:imum)?|budget(?: of)?)\s*"
        r"[$€£]?\s*(\d{2,5})\b",
        lowered,
    )
    if budget_match:
        updated.max_price = int(budget_match.group(1))

    return updated, ""
