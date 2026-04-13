"""
liturgical.py — Catholic liturgical calendar lookup for Greenlough URL prediction.
"""
from datetime import date

# 2026 Catholic Liturgical Calendar — Sunday names
# Used to predict Greenlough parish bulletin URLs which embed the liturgical name.
LITURGICAL_SUNDAYS_2026: dict[date, str] = {
    date(2026, 1, 4): "Epiphany_of_the_Lord",
    date(2026, 1, 11): "Baptism_of_the_Lord",
    date(2026, 1, 18): "2nd_Sunday_in_Ordinary_Time",
    date(2026, 1, 25): "3rd_Sunday_in_Ordinary_Time",
    date(2026, 2, 1): "4th_Sunday_in_Ordinary_Time",
    date(2026, 2, 8): "5th_Sunday_in_Ordinary_Time",
    date(2026, 2, 15): "Sixth_Sunday_in_Ordinary_Time",
    date(2026, 2, 22): "1st_Sunday_of_Lent",
    date(2026, 3, 1): "2nd_Sunday_of_Lent",
    date(2026, 3, 8): "3rd_Sunday_of_Lent",
    date(2026, 3, 15): "4th_Sunday_of_Lent",
    date(2026, 3, 22): "5th_Sunday_of_Lent",
    date(2026, 3, 29): "Palm_Sunday",
    date(2026, 4, 5): "Easter_Sunday_2026",
    date(2026, 4, 12): "2nd_Sunday_of_Easter_-_Divine_Mercy_Sunday",
    date(2026, 4, 19): "3rd_Sunday_of_Easter",
    date(2026, 4, 26): "4th_Sunday_of_Easter",
    date(2026, 5, 3): "5th_Sunday_of_Easter",
    date(2026, 5, 10): "6th_Sunday_of_Easter",
    date(2026, 5, 17): "7th_Sunday_of_Easter",
    date(2026, 5, 24): "Pentecost_Sunday",
    date(2026, 5, 31): "Trinity_Sunday",
    date(2026, 6, 7): "The_Most_Holy_Body_and_Blood_of_Christ",
    date(2026, 6, 14): "11th_Sunday_in_Ordinary_Time",
    date(2026, 6, 21): "12th_Sunday_in_Ordinary_Time",
    date(2026, 6, 28): "13th_Sunday_in_Ordinary_Time",
    date(2026, 7, 5): "14th_Sunday_in_Ordinary_Time",
    date(2026, 7, 12): "15th_Sunday_in_Ordinary_Time",
    date(2026, 7, 19): "16th_Sunday_in_Ordinary_Time",
    date(2026, 7, 26): "17th_Sunday_in_Ordinary_Time",
    date(2026, 8, 2): "18th_Sunday_in_Ordinary_Time",
    date(2026, 8, 9): "19th_Sunday_in_Ordinary_Time",
    date(2026, 8, 16): "20th_Sunday_in_Ordinary_Time",
    date(2026, 8, 23): "21st_Sunday_in_Ordinary_Time",
    date(2026, 8, 30): "22nd_Sunday_in_Ordinary_Time",
    date(2026, 9, 6): "23rd_Sunday_in_Ordinary_Time",
    date(2026, 9, 13): "24th_Sunday_in_Ordinary_Time",
    date(2026, 9, 20): "25th_Sunday_in_Ordinary_Time",
    date(2026, 9, 27): "26th_Sunday_in_Ordinary_Time",
    date(2026, 10, 4): "27th_Sunday_in_Ordinary_Time",
    date(2026, 10, 11): "28th_Sunday_in_Ordinary_Time",
    date(2026, 10, 18): "29th_Sunday_in_Ordinary_Time",
    date(2026, 10, 25): "30th_Sunday_in_Ordinary_Time",
    date(2026, 11, 1): "All_Saints_Day",
    date(2026, 11, 8): "32nd_Sunday_in_Ordinary_Time",
    date(2026, 11, 15): "33rd_Sunday_in_Ordinary_Time",
    date(2026, 11, 22): "Our_Lord_Jesus_Christ_King_of_the_Universe",
    date(2026, 11, 29): "1st_Sunday_of_Advent",
    date(2026, 12, 6): "2nd_Sunday_of_Advent",
    date(2026, 12, 13): "3rd_Sunday_of_Advent",
    date(2026, 12, 20): "4th_Sunday_of_Advent",
    date(2026, 12, 25): "Christmas_Day",
    date(2026, 12, 27): "The_Holy_Family",
}


def get_liturgical_name(target: date) -> str | None:
    """Return the liturgical Sunday name for the given date, or None if not found."""
    return LITURGICAL_SUNDAYS_2026.get(target)
