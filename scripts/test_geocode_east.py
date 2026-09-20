"""Проверка подготовки адресов и отсечения непроверенных домов."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.geocode_east import pick, search_query, write_review


class GeocodeEastTest(unittest.TestCase):
    def test_query_separates_street_type_and_name(self) -> None:
        self.assertEqual(
            search_query("Город Москва, пр-кт.Волгоградский, д. 128 к 5"),
            "Москва, проспект Волгоградский, 128 к 5",
        )

    def test_only_matching_house_is_accepted(self) -> None:
        address = "Город Москва, ул.Международная, д. 28 стр. 1"
        matches = [
            {"address": {"house_number": "28"}, "lat": "55.1", "lon": "37.1"},
            {"address": {"house_number": "28с1"}, "lat": "55.2", "lon": "37.2"},
        ]
        self.assertEqual(pick(address, matches)["latitude"], 55.2)
        self.assertEqual(pick(address, matches[:1])["status"], "review_required")

    def test_review_contains_only_unconfirmed_addresses(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            count = write_review(
                path,
                ["точный", "сомнительный"],
                {
                    "точный": {"status": "exact_house"},
                    "сомнительный": {"status": "not_found"},
                },
            )
            self.assertEqual(count, 1)
            self.assertIn("сомнительный", path.read_text(encoding="utf-8"))
            self.assertNotIn("точный", path.read_text(encoding="utf-8"))

    def test_review_keeps_manual_coordinates(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            path.write_text(
                "адрес,статус,широта_проверенная,долгота_проверенная\n"
                "адрес,not_found,55.7,37.8\n",
                encoding="utf-8",
            )
            write_review(path, ["адрес"], {"адрес": {"status": "not_found"}})
            self.assertIn("55.7,37.8", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
