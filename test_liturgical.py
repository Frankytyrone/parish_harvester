from __future__ import annotations

import unittest
from datetime import date

from harvester.liturgical import get_liturgical_name, get_liturgical_sundays
from harvester.utils import rewrite_greenlough_url


class LiturgicalCalendarTests(unittest.TestCase):
    def test_2026_calendar_matches_previous_hardcoded_map_exactly(self) -> None:
        expected = {
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
        self.assertEqual(get_liturgical_sundays(2026), expected)

    def test_2027_uses_dynamic_easter_and_divine_mercy_naming(self) -> None:
        self.assertEqual(get_liturgical_name(date(2027, 3, 28)), "Easter_Sunday_2027")
        self.assertEqual(
            get_liturgical_name(date(2027, 4, 4)),
            "2nd_Sunday_of_Easter_-_Divine_Mercy_Sunday",
        )

    def test_rewrite_greenlough_url_uses_dynamic_liturgical_name(self) -> None:
        original = "http://www.greenlough.com/publications/newsletter/Easter_Sunday_2026_[2026-4-5].pdf"
        rewritten = rewrite_greenlough_url(original, date(2027, 3, 28))
        self.assertEqual(
            rewritten,
            "http://www.greenlough.com/publications/newsletter/Easter_Sunday_2027_[2027-3-28].pdf",
        )


if __name__ == "__main__":
    unittest.main()
