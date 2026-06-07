"""دیتاست state/city برای هر کشور (سازگار با SmartProxy).

نام‌ها به‌صورت CamelCase و بدون فاصله‌اند چون SmartProxy فاصله نمی‌پذیرد
(مثلاً area-US_state-California_city-LosAngeles). برای نمایش در ربات با
prettify فاصله‌گذاری می‌شوند.

کشورهایی که اینجا نیستند، state/city به‌صورت «تصادفی» در نظر گرفته می‌شوند.
"""
from __future__ import annotations

import re

# country_code -> { state_name: [city_names] }
LOCATIONS: dict[str, dict[str, list[str]]] = {
    "US": {
        "California": ["LosAngeles", "SanFrancisco", "SanDiego"],
        "NewYork": ["NewYork", "Buffalo"],
        "Texas": ["Houston", "Dallas"],
        "Florida": ["Miami", "Orlando"],
        "Illinois": ["Chicago", "Springfield"],
    },
    "GB": {
        "England": ["London", "Manchester", "Birmingham"],
        "Scotland": ["Glasgow", "Edinburgh"],
        "Wales": ["Cardiff", "Swansea"],
        "NorthernIreland": ["Belfast"],
    },
    "DE": {
        "Berlin": ["Berlin"],
        "Bavaria": ["Munich", "Nuremberg"],
        "Hesse": ["Frankfurt"],
        "Hamburg": ["Hamburg"],
        "NorthRhineWestphalia": ["Cologne", "Dusseldorf"],
    },
    "FR": {
        "IleDeFrance": ["Paris"],
        "ProvenceAlpesCoteDazur": ["Marseille", "Nice"],
        "AuvergneRhoneAlpes": ["Lyon"],
        "Occitanie": ["Toulouse"],
    },
    "NL": {
        "NorthHolland": ["Amsterdam"],
        "SouthHolland": ["Rotterdam", "TheHague"],
        "Utrecht": ["Utrecht"],
    },
    "CA": {
        "Ontario": ["Toronto", "Ottawa"],
        "Quebec": ["Montreal", "QuebecCity"],
        "BritishColumbia": ["Vancouver"],
        "Alberta": ["Calgary", "Edmonton"],
    },
    "TR": {
        "Istanbul": ["Istanbul"],
        "Ankara": ["Ankara"],
        "Izmir": ["Izmir"],
    },
    "AE": {
        "Dubai": ["Dubai"],
        "AbuDhabi": ["AbuDhabi"],
    },
    "IT": {
        "Lazio": ["Rome"],
        "Lombardy": ["Milan"],
        "Campania": ["Naples"],
    },
    "ES": {
        "Madrid": ["Madrid"],
        "Catalonia": ["Barcelona"],
        "Andalusia": ["Seville", "Malaga"],
    },
    "SE": {
        "Stockholm": ["Stockholm"],
        "VastraGotaland": ["Gothenburg"],
    },
    "PL": {
        "Masovia": ["Warsaw"],
        "LesserPoland": ["Krakow"],
    },
    "JP": {
        "Tokyo": ["Tokyo"],
        "Osaka": ["Osaka"],
    },
    "SG": {
        "Singapore": ["Singapore"],
    },
    "AU": {
        "NewSouthWales": ["Sydney"],
        "Victoria": ["Melbourne"],
        "Queensland": ["Brisbane"],
    },
    "FI": {
        "Uusimaa": ["Helsinki"],
    },
}


def has_states(country: str) -> bool:
    return bool(LOCATIONS.get((country or "").upper()))


def states(country: str) -> list[str]:
    return list(LOCATIONS.get((country or "").upper(), {}).keys())


def cities(country: str, state: str) -> list[str]:
    return list(LOCATIONS.get((country or "").upper(), {}).get(state or "", []))


def has_cities(country: str, state: str) -> bool:
    return bool(cities(country, state))


def prettify(name: str) -> str:
    """CamelCase را برای نمایش با فاصله جدا می‌کند: LosAngeles -> Los Angeles."""
    if not name:
        return name
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name)
