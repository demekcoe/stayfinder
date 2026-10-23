import json
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from google.genai.errors import APIError
from google.genai._gaos.lib.compat_errors import InternalServerError
from httpx import Request, Response

from app import (
    Criteria,
    ChatRequest,
    Interpretation,
    chat,
    health_check,
    interpret_with_gemini,
    update_criteria,
)
from hotels import search_hotels


class HotelAgentTests(unittest.TestCase):
    def test_health_check_reports_ok(self) -> None:
        self.assertEqual(health_check(), {"status": "ok"})

    def test_collects_search_criteria_from_message(self) -> None:
        criteria, note = update_criteria(
            "Paris from 2026-11-05 to 2026-11-08 for 2 guests under $250",
            Criteria(),
        )

        self.assertEqual(note, "")
        self.assertEqual(criteria.destination, "Paris")
        self.assertEqual(criteria.check_in, date(2026, 11, 5))
        self.assertEqual(criteria.check_out, date(2026, 11, 8))
        self.assertEqual(criteria.guests, 2)
        self.assertEqual(criteria.max_price, 250)

    def test_asks_for_missing_information(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = chat(ChatRequest(message="I'd like to travel to Tokyo"))

        self.assertIn("check-in and check-out dates", response.reply)
        self.assertIn("number of guests", response.reply)
        self.assertIn("AI interpretation is not enabled", response.reply)
        self.assertEqual(response.criteria.destination, "Tokyo")
        self.assertEqual(response.hotels, [])

    def test_template_placeholder_does_not_enable_gemini(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "put-your-key-here"}):
            response = chat(ChatRequest(message="I'd like to travel to Tokyo"))

        self.assertIn("GEMINI_API_KEY is not set", response.reply)

    def test_uses_model_interpretation_for_conversational_messages(self) -> None:
        interpretation = Interpretation(
            criteria=Criteria(
                destination="Paris",
                check_in=date(2026, 11, 7),
                check_out=date(2026, 11, 9),
                guests=2,
                max_price=250,
            )
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("app.interpret_with_gemini", return_value=interpretation) as interpret,
        ):
            response = chat(ChatRequest(
                message="Somewhere in Paris next weekend for me and my partner, ideally under $250",
            ))

        interpret.assert_called_once()
        self.assertIn("Here are sample stays in Paris", response.reply)
        self.assertEqual(response.criteria.guests, 2)
        self.assertTrue(response.hotels)

    def test_returns_model_clarification_before_searching(self) -> None:
        interpretation = Interpretation(
            criteria=Criteria(),
            clarification="Which city did you have in mind?",
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("app.interpret_with_gemini", return_value=interpretation),
        ):
            response = chat(ChatRequest(message="Somewhere warm for next weekend"))

        self.assertEqual(response.reply, "Which city did you have in mind?")
        self.assertEqual(response.hotels, [])

    def test_gemini_response_is_parsed_into_validated_criteria(self) -> None:
        content = json.dumps({
            "criteria": {
                "destination": "Paris",
                "check_in": "2026-11-07",
                "check_out": "2026-11-09",
                "guests": 2,
                "max_price": 250,
            },
            "clarification": None,
        })
        client = Mock()
        client.interactions.create.return_value = SimpleNamespace(output_text=content)
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("google.genai.Client", return_value=client),
        ):
            result = interpret_with_gemini("Paris next weekend for two", Criteria())

        self.assertEqual(result.criteria.destination, "Paris")
        self.assertEqual(result.criteria.check_in, date(2026, 11, 7))
        self.assertEqual(result.criteria.guests, 2)

    def test_gemini_quota_error_gives_actionable_message(self) -> None:
        error = APIError(code=429, response_json={"message": "quota exceeded"})
        client = Mock()
        client.interactions.create.side_effect = error

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("google.genai.Client", return_value=client),
        ):
            with self.assertRaises(HTTPException) as raised:
                interpret_with_gemini("Paris for two", Criteria())

        self.assertIn("Gemini API rate limit or quota", raised.exception.detail)
        self.assertIn("Google AI Studio", raised.exception.detail)

    def test_gemini_overload_error_is_reported_as_temporary(self) -> None:
        response = Response(
            status_code=503,
            request=Request("POST", "https://generativelanguage.googleapis.com"),
        )
        error = InternalServerError(
            "Gemini is experiencing high demand",
            response=response,
            body={"error": {"message": "Gemini is experiencing high demand"}},
        )
        client = Mock()
        client.interactions.create.side_effect = error

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("google.genai.Client", return_value=client),
        ):
            with self.assertRaises(HTTPException) as raised:
                interpret_with_gemini("Paris for two", Criteria())

        self.assertIn("temporarily busy", raised.exception.detail)
        self.assertIn("try sending your message again", raised.exception.detail)

    def test_returns_only_matching_hotels(self) -> None:
        criteria = Criteria(
            destination="Paris",
            check_in=date(2026, 11, 5),
            check_out=date(2026, 11, 8),
            guests=2,
            max_price=200,
        )

        results = search_hotels(criteria)

        self.assertEqual([hotel["name"] for hotel in results], ["Canal Corner Hotel"])

    def test_rejects_checkout_before_checkin_and_resets_dates(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = chat(ChatRequest(
                message="Paris 2026-11-08 to 2026-11-05 for 2 guests",
            ))

        self.assertIn("must be after check-in", response.reply)
        self.assertIsNone(response.criteria.check_in)
        self.assertIsNone(response.criteria.check_out)


if __name__ == "__main__":
    unittest.main()
