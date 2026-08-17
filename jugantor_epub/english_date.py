from datetime import date


def format_english_date(iso_date):
    """Format an ISO date string ("2026-08-17") as an English-language date
    string ("17 August, 2026") for display in the epub."""
    parsed = date.fromisoformat(iso_date)
    return f"{parsed.day} {parsed.strftime('%B')}, {parsed.year}"
