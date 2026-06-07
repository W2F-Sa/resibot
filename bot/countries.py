"""لیست کامل کشورها (ISO 3166-1 alpha-2) + جستجو + پرچم.

پرچم به‌صورت داینامیک از روی کد کشور ساخته می‌شود (regional indicators)،
پس نیازی به هاردکد کردن پرچم‌ها نیست.
"""
from __future__ import annotations

# (code, english_name)
ALL_COUNTRIES: list[tuple[str, str]] = [
    ("AF", "Afghanistan"), ("AL", "Albania"), ("DZ", "Algeria"), ("AD", "Andorra"),
    ("AO", "Angola"), ("AR", "Argentina"), ("AM", "Armenia"), ("AU", "Australia"),
    ("AT", "Austria"), ("AZ", "Azerbaijan"), ("BH", "Bahrain"), ("BD", "Bangladesh"),
    ("BY", "Belarus"), ("BE", "Belgium"), ("BZ", "Belize"), ("BJ", "Benin"),
    ("BT", "Bhutan"), ("BO", "Bolivia"), ("BA", "Bosnia and Herzegovina"),
    ("BW", "Botswana"), ("BR", "Brazil"), ("BN", "Brunei"), ("BG", "Bulgaria"),
    ("BF", "Burkina Faso"), ("KH", "Cambodia"), ("CM", "Cameroon"), ("CA", "Canada"),
    ("CL", "Chile"), ("CN", "China"), ("CO", "Colombia"), ("CR", "Costa Rica"),
    ("HR", "Croatia"), ("CU", "Cuba"), ("CY", "Cyprus"), ("CZ", "Czechia"),
    ("DK", "Denmark"), ("DO", "Dominican Republic"), ("EC", "Ecuador"), ("EG", "Egypt"),
    ("SV", "El Salvador"), ("EE", "Estonia"), ("ET", "Ethiopia"), ("FI", "Finland"),
    ("FR", "France"), ("GE", "Georgia"), ("DE", "Germany"), ("GH", "Ghana"),
    ("GR", "Greece"), ("GT", "Guatemala"), ("HN", "Honduras"), ("HK", "Hong Kong"),
    ("HU", "Hungary"), ("IS", "Iceland"), ("IN", "India"), ("ID", "Indonesia"),
    ("IR", "Iran"), ("IQ", "Iraq"), ("IE", "Ireland"), ("IL", "Israel"),
    ("IT", "Italy"), ("CI", "Ivory Coast"), ("JM", "Jamaica"), ("JP", "Japan"),
    ("JO", "Jordan"), ("KZ", "Kazakhstan"), ("KE", "Kenya"), ("KW", "Kuwait"),
    ("KG", "Kyrgyzstan"), ("LA", "Laos"), ("LV", "Latvia"), ("LB", "Lebanon"),
    ("LY", "Libya"), ("LI", "Liechtenstein"), ("LT", "Lithuania"), ("LU", "Luxembourg"),
    ("MO", "Macau"), ("MK", "North Macedonia"), ("MG", "Madagascar"), ("MY", "Malaysia"),
    ("MV", "Maldives"), ("MT", "Malta"), ("MX", "Mexico"), ("MD", "Moldova"),
    ("MC", "Monaco"), ("MN", "Mongolia"), ("ME", "Montenegro"), ("MA", "Morocco"),
    ("MM", "Myanmar"), ("NP", "Nepal"), ("NL", "Netherlands"), ("NZ", "New Zealand"),
    ("NI", "Nicaragua"), ("NG", "Nigeria"), ("NO", "Norway"), ("OM", "Oman"),
    ("PK", "Pakistan"), ("PA", "Panama"), ("PY", "Paraguay"), ("PE", "Peru"),
    ("PH", "Philippines"), ("PL", "Poland"), ("PT", "Portugal"), ("QA", "Qatar"),
    ("RO", "Romania"), ("RU", "Russia"), ("SA", "Saudi Arabia"), ("SN", "Senegal"),
    ("RS", "Serbia"), ("SG", "Singapore"), ("SK", "Slovakia"), ("SI", "Slovenia"),
    ("ZA", "South Africa"), ("KR", "South Korea"), ("ES", "Spain"), ("LK", "Sri Lanka"),
    ("SE", "Sweden"), ("CH", "Switzerland"), ("TW", "Taiwan"), ("TJ", "Tajikistan"),
    ("TZ", "Tanzania"), ("TH", "Thailand"), ("TN", "Tunisia"), ("TR", "Turkey"),
    ("TM", "Turkmenistan"), ("UG", "Uganda"), ("UA", "Ukraine"),
    ("AE", "United Arab Emirates"), ("GB", "United Kingdom"), ("US", "United States"),
    ("UY", "Uruguay"), ("UZ", "Uzbekistan"), ("VE", "Venezuela"), ("VN", "Vietnam"),
    ("YE", "Yemen"), ("ZM", "Zambia"), ("ZW", "Zimbabwe"),
]

# نام فارسی برای کشورهای پرکاربرد (بقیه نام انگلیسی نمایش داده می‌شوند)
NAMES_FA: dict[str, str] = {
    "GB": "انگلستان", "US": "آمریکا", "DE": "آلمان", "FR": "فرانسه",
    "NL": "هلند", "CA": "کانادا", "TR": "ترکیه", "AE": "امارات",
    "IT": "ایتالیا", "ES": "اسپانیا", "SE": "سوئد", "PL": "لهستان",
    "JP": "ژاپن", "SG": "سنگاپور", "AU": "استرالیا", "RU": "روسیه",
    "CN": "چین", "IN": "هند", "IR": "ایران", "CH": "سوئیس",
    "AT": "اتریش", "BE": "بلژیک", "FI": "فنلاند", "NO": "نروژ",
    "DK": "دانمارک", "IE": "ایرلند", "PT": "پرتغال", "KR": "کره جنوبی",
    "HK": "هنگ‌کنگ", "TW": "تایوان", "BR": "برزیل", "MX": "مکزیک",
    "QA": "قطر", "SA": "عربستان", "KW": "کویت", "AZ": "آذربایجان",
    "AM": "ارمنستان", "GE": "گرجستان", "UA": "اوکراین", "RO": "رومانی",
    "CZ": "چک", "HU": "مجارستان", "GR": "یونان", "TH": "تایلند",
    "MY": "مالزی", "ID": "اندونزی", "VN": "ویتنام", "PH": "فیلیپین",
    "ZA": "آفریقای جنوبی", "EG": "مصر", "IL": "اسرائیل", "KZ": "قزاقستان",
}

# کشورهای پرکاربرد برای دکمه‌های سریع
POPULAR_CODES: list[str] = [
    "GB", "US", "DE", "FR", "NL", "CA", "TR", "AE",
    "IT", "ES", "SE", "PL", "JP", "SG", "AU", "FI",
]

_NAME_BY_CODE = {code: name for code, name in ALL_COUNTRIES}


def flag(code: str) -> str:
    """پرچم emoji را از روی کد دو حرفی می‌سازد."""
    code = code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def display_name(code: str) -> str:
    code = code.upper()
    return NAMES_FA.get(code) or _NAME_BY_CODE.get(code, code)


def label(code: str) -> str:
    return f"{flag(code)} {display_name(code)}"


def popular() -> list[tuple[str, str]]:
    return [(c, label(c)) for c in POPULAR_CODES]


def search(query: str, limit: int = 18) -> list[tuple[str, str]]:
    """جستجو بر اساس کد، نام انگلیسی یا نام فارسی."""
    q = query.strip().lower()
    if not q:
        return []
    results: list[tuple[str, str]] = []
    for code, en in ALL_COUNTRIES:
        fa = NAMES_FA.get(code, "")
        if q == code.lower() or q in en.lower() or (fa and q in fa.lower()):
            results.append((code, label(code)))
        if len(results) >= limit:
            break
    return results


def is_valid_code(code: str) -> bool:
    return code.upper() in _NAME_BY_CODE
