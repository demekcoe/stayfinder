from typing import Any


HOTELS: list[dict[str, Any]] = [
    {
        "name": "Canal Corner Hotel",
        "city": "Paris",
        "nightly_rate": 189,
        "max_guests": 2,
        "rating": 4.6,
        "amenities": ["Wi-Fi", "Breakfast", "City view"],
        "description": "A cozy base near the Canal Saint-Martin.",
    },
    {
        "name": "Left Bank House",
        "city": "Paris",
        "nightly_rate": 245,
        "max_guests": 4,
        "rating": 4.8,
        "amenities": ["Wi-Fi", "Family rooms", "Breakfast"],
        "description": "A relaxed stay within reach of the Latin Quarter.",
    },
    {
        "name": "Trastevere Rooms",
        "city": "Rome",
        "nightly_rate": 156,
        "max_guests": 3,
        "rating": 4.5,
        "amenities": ["Wi-Fi", "Air conditioning", "Terrace"],
        "description": "A small guesthouse in the heart of Trastevere.",
    },
    {
        "name": "Forum Garden Hotel",
        "city": "Rome",
        "nightly_rate": 218,
        "max_guests": 4,
        "rating": 4.7,
        "amenities": ["Wi-Fi", "Breakfast", "Garden"],
        "description": "A quiet hotel a short walk from historic sights.",
    },
    {
        "name": "Shinjuku Stay",
        "city": "Tokyo",
        "nightly_rate": 132,
        "max_guests": 2,
        "rating": 4.4,
        "amenities": ["Wi-Fi", "Air conditioning", "Transit nearby"],
        "description": "A compact, convenient stay close to major rail links.",
    },
    {
        "name": "Maple Midtown Inn",
        "city": "New York",
        "nightly_rate": 279,
        "max_guests": 3,
        "rating": 4.3,
        "amenities": ["Wi-Fi", "Gym", "Transit nearby"],
        "description": "A practical Midtown option near theaters and transit.",
    },
]


def search_hotels(criteria: Any) -> list[dict[str, Any]]:
    matches = [
        hotel
        for hotel in HOTELS
        if hotel["city"].casefold() == criteria.destination.casefold()
        and hotel["max_guests"] >= criteria.guests
        and (criteria.max_price is None or hotel["nightly_rate"] <= criteria.max_price)
    ]
    return sorted(matches, key=lambda hotel: (-hotel["rating"], hotel["nightly_rate"]))
