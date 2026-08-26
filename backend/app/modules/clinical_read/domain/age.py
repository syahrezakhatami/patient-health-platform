from datetime import date


def age_years(birth_date: date, as_of: date) -> int:
    """Gregorian whole years using the UTC calendar date of the request."""
    years = as_of.year - birth_date.year
    if (as_of.month, as_of.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years
