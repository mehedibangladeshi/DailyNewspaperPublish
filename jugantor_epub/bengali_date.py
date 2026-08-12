from datetime import date

_DIGIT_MAP = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

_MONTH_NAMES = {
    1: "জানুয়ারি",
    2: "ফেব্রুয়ারি",
    3: "মার্চ",
    4: "এপ্রিল",
    5: "মে",
    6: "জুন",
    7: "জুলাই",
    8: "আগস্ট",
    9: "সেপ্টেম্বর",
    10: "অক্টোবর",
    11: "নভেম্বর",
    12: "ডিসেম্বর",
}


def format_bengali_date(iso_date):
    """Format an ISO date string ("2026-08-12") as a Bengali-language date
    string ("১২ আগস্ট, ২০২৬") for display in the epub."""
    parsed = date.fromisoformat(iso_date)
    day_bn = f"{parsed.day:02d}".translate(_DIGIT_MAP)
    year_bn = str(parsed.year).translate(_DIGIT_MAP)
    return f"{day_bn} {_MONTH_NAMES[parsed.month]}, {year_bn}"
