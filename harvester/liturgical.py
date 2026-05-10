"""
liturgical.py — Catholic liturgical calendar lookup for Greenlough URL prediction.
"""
from datetime import date, timedelta
from functools import lru_cache


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _ordinary_time_name(week: int) -> str:
    if week == 6:
        return "Sixth_Sunday_in_Ordinary_Time"
    return f"{_ordinal(week)}_Sunday_in_Ordinary_Time"


def _easter_sunday(year: int) -> date:
    """
    Return Gregorian Easter Sunday for *year* (Anonymous Gregorian computus).
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _next_sunday(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()) % 7)


@lru_cache(maxsize=None)
def get_liturgical_sundays(year: int) -> dict[date, str]:
    """
    Build liturgical Sunday names for *year* in the Greenlough filename format.
    """
    names: dict[date, str] = {}

    easter = _easter_sunday(year)
    epiphany = _next_sunday(date(year, 1, 2))
    baptism = epiphany + timedelta(days=7)
    lent_1 = easter - timedelta(days=42)
    palm = easter - timedelta(days=7)
    pentecost = easter + timedelta(days=49)
    trinity = easter + timedelta(days=56)
    corpus = easter + timedelta(days=63)
    first_advent = _next_sunday(date(year, 11, 27))
    christ_king = first_advent - timedelta(days=7)
    all_saints = date(year, 11, 1)
    christmas = date(year, 12, 25)

    names[epiphany] = "Epiphany_of_the_Lord"
    names[baptism] = "Baptism_of_the_Lord"

    # Ordinary Time before Lent starts.
    cur = baptism + timedelta(days=7)
    week = 2
    while cur < lent_1:
        names[cur] = _ordinary_time_name(week)
        cur += timedelta(days=7)
        week += 1

    names[lent_1] = "1st_Sunday_of_Lent"
    names[lent_1 + timedelta(days=7)] = "2nd_Sunday_of_Lent"
    names[lent_1 + timedelta(days=14)] = "3rd_Sunday_of_Lent"
    names[lent_1 + timedelta(days=21)] = "4th_Sunday_of_Lent"
    names[lent_1 + timedelta(days=28)] = "5th_Sunday_of_Lent"
    names[palm] = "Palm_Sunday"
    names[easter] = f"Easter_Sunday_{year}"
    names[easter + timedelta(days=7)] = "2nd_Sunday_of_Easter_-_Divine_Mercy_Sunday"
    names[easter + timedelta(days=14)] = "3rd_Sunday_of_Easter"
    names[easter + timedelta(days=21)] = "4th_Sunday_of_Easter"
    names[easter + timedelta(days=28)] = "5th_Sunday_of_Easter"
    names[easter + timedelta(days=35)] = "6th_Sunday_of_Easter"
    names[easter + timedelta(days=42)] = "7th_Sunday_of_Easter"
    names[pentecost] = "Pentecost_Sunday"
    names[trinity] = "Trinity_Sunday"
    names[corpus] = "The_Most_Holy_Body_and_Blood_of_Christ"

    # Ordinary Time after Corpus Christi to Christ the King.
    ordinary_slots_after_corpus: list[date] = []
    cur = corpus + timedelta(days=7)
    while cur < christ_king:
        ordinary_slots_after_corpus.append(cur)
        cur += timedelta(days=7)

    starting_week = 33 - (len(ordinary_slots_after_corpus) - 1)
    for i, sunday in enumerate(ordinary_slots_after_corpus):
        if sunday not in names and sunday != all_saints:
            names[sunday] = _ordinary_time_name(starting_week + i)

    if all_saints.weekday() == 6:
        names[all_saints] = "All_Saints_Day"

    names[christ_king] = "Our_Lord_Jesus_Christ_King_of_the_Universe"
    names[first_advent] = "1st_Sunday_of_Advent"
    names[first_advent + timedelta(days=7)] = "2nd_Sunday_of_Advent"
    names[first_advent + timedelta(days=14)] = "3rd_Sunday_of_Advent"
    names[first_advent + timedelta(days=21)] = "4th_Sunday_of_Advent"
    names[christmas] = "Christmas_Day"

    # Sunday in the octave of Christmas; if absent, celebrated on Dec 30.
    holy_family = _next_sunday(christmas + timedelta(days=1))
    if holy_family.year != year:
        holy_family = date(year, 12, 30)
    names[holy_family] = "The_Holy_Family"
    return names


def get_liturgical_name(target: date) -> str | None:
    """Return the liturgical Sunday name for the given date, or None if not found."""
    return get_liturgical_sundays(target.year).get(target)
