from datetime import date

from app.query_parser import parse_rules

TODAY = date(2026, 11, 1)


def test_amount_and_kind():
    f = parse_rules("receipts over 40 euros", TODAY)
    assert f.min_amount == 40 and f.semantic_query == "receipts"


def test_month_year_and_photos():
    f = parse_rules("photos of the beach in July 2025", TODAY)
    assert (f.date_from, f.date_to) == (date(2025, 7, 1), date(2025, 7, 31))
    assert f.kind == "photo"
    assert f.semantic_query == "beach"


def test_last_summer_and_bare_month_defaults_to_past():
    f = parse_rules("hiking last summer", TODAY)
    assert (f.date_from, f.date_to) == (date(2025, 6, 1), date(2025, 8, 31))
    f = parse_rules("dinner in december", TODAY)  # December hasn't happened yet this year
    assert f.date_from == date(2025, 12, 1)


def test_relative_and_year():
    assert parse_rules("documents from last year", TODAY).date_from == date(2025, 1, 1)
    assert parse_rules("documents from last year", TODAY).kind == "document"
    assert parse_rules("2024 warranty", TODAY).date_to == date(2024, 12, 31)


def test_plain_query_untouched():
    f = parse_rules("black hoodie", TODAY)
    assert f.semantic_query == "black hoodie" and not f.has_filters()


def test_bare_season_is_most_recent_and_adjectives_stay_semantic():
    f = parse_rules("photos from winter", TODAY)  # winter 2026/27 hasn't started yet
    assert (f.date_from, f.date_to) == (date(2025, 12, 1), date(2026, 2, 28))
    f = parse_rules("winter street covered in snow", TODAY)  # descriptive, not a date
    assert f.date_from is None and "winter" in f.semantic_query
