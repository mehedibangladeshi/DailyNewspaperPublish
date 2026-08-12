import pytest

from jugantor_epub import bengali_date


def test_format_bengali_date_converts_digits_and_month_name():
    assert bengali_date.format_bengali_date("2026-08-12") == "১২ আগস্ট, ২০২৬"


@pytest.mark.parametrize(
    "iso_date, expected_month",
    [
        ("2026-01-05", "জানুয়ারি"),
        ("2026-02-05", "ফেব্রুয়ারি"),
        ("2026-03-05", "মার্চ"),
        ("2026-04-05", "এপ্রিল"),
        ("2026-05-05", "মে"),
        ("2026-06-05", "জুন"),
        ("2026-07-05", "জুলাই"),
        ("2026-09-05", "সেপ্টেম্বর"),
        ("2026-10-05", "অক্টোবর"),
        ("2026-11-05", "নভেম্বর"),
        ("2026-12-05", "ডিসেম্বর"),
    ],
)
def test_format_bengali_date_maps_every_month_name(iso_date, expected_month):
    assert expected_month in bengali_date.format_bengali_date(iso_date)


def test_format_bengali_date_converts_single_digit_day_to_bengali_digits():
    assert bengali_date.format_bengali_date("2026-01-05") == "০৫ জানুয়ারি, ২০২৬"
