from jugantor_epub import english_date


def test_format_english_date_formats_day_month_year():
    assert english_date.format_english_date("2026-08-17") == "17 August, 2026"


def test_format_english_date_does_not_zero_pad_single_digit_day():
    assert english_date.format_english_date("2026-01-05") == "5 January, 2026"
