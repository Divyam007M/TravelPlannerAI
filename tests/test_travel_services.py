import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from backend import travel_services as services


PARIS_FR = {"name": "Paris", "admin1": "Île-de-France", "country": "France", "country_code": "FR",
            "latitude": 48.8534, "longitude": 2.3488, "timezone": "Europe/Paris"}
PARIS_TX = {"name": "Paris", "admin1": "Texas", "country": "United States", "country_code": "US",
            "latitude": 33.66, "longitude": -95.56, "timezone": "America/Chicago"}
TOKYO = {"name": "Tokyo", "admin1": "Tokyo", "country": "Japan", "country_code": "JP",
         "latitude": 35.68, "longitude": 139.69, "timezone": "Asia/Tokyo"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        services._cache = services._Cache()

    def test_global_location_ambiguity_qualifier_and_unknown(self):
        with patch.object(services, "_fetch_json", return_value={"results": [PARIS_FR, PARIS_TX]}):
            ambiguous = services.resolve_location("Paris")
            self.assertEqual(ambiguous["status"], "ambiguous")
            self.assertIn("Paris, Texas", ambiguous["message"])
            france = services.resolve_location("Paris, France")
            self.assertEqual(france["location"]["usual_currency"], "EUR")
            self.assertEqual(france["location"]["timezone"], "Europe/Paris")
            texas = services.resolve_location("Paris, Texas")
            self.assertEqual(texas["location"]["usual_currency"], "USD")
            self.assertEqual(texas["location"]["longitude"], -95.56)
        with patch.object(services, "_fetch_json", return_value={}):
            self.assertEqual(services.resolve_location("Atlantis")["status"], "not_found")
        with patch.object(services, "_fetch_json", side_effect=services.ServiceUnavailable()):
            self.assertEqual(services.resolve_location("Unmapped Place")["status"], "unavailable")

    def test_weather_dates_horizon_and_failure(self):
        forecast = {"timezone": "Asia/Tokyo", "current": {"time": "2026-09-29T12:00", "temperature_2m": 22},
                    "daily": {"time": ["2026-09-29", "2026-09-30", "2026-10-01"],
                              "temperature_2m_min": [16, 17, 18], "temperature_2m_max": [22, 23, 24],
                              "precipitation_sum": [0, 2, 4],
                              "precipitation_probability_max": [10, 30, 50], "weather_code": [0, 2, 3]}}
        with patch.object(services, "_fetch_json", side_effect=[{"results": [TOKYO]}, forecast]) as fetch, \
             patch.object(services, "_local_today", return_value=date(2026, 9, 29)), \
             patch.object(services, "_utc_now", return_value=datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)):
            result = services.weather_forecast("Tokyo, Japan", "2026-09-30", 2)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["timezone"], "Asia/Tokyo")
            self.assertEqual(result["forecast"][0]["precipitation_mm"], 2)
            self.assertEqual(result["forecast"][0]["condition"], "Partly cloudy")
            self.assertIsNone(result["current"])
            self.assertIn("2026-09-29", result["retrieved_at_utc"])
            beyond = services.weather_forecast("Tokyo, Japan", "2026-11-01", 2)
            self.assertEqual(beyond["status"], "outside_horizon")
            self.assertEqual(services.weather_forecast("Tokyo, Japan", "bad-date")["status"], "invalid")
            self.assertEqual(fetch.call_count, 2)  # no forecast call beyond horizon
        services._cache = services._Cache()
        with patch.object(services, "_fetch_json", side_effect=[{"results": [TOKYO]}, services.ServiceUnavailable()]):
            self.assertEqual(services.weather_forecast("Tokyo", "2026-09-30")["status"], "unavailable")

    def test_exchange_rate_date_math_cache_and_failure(self):
        rate = {"date": "2026-09-28", "base": "INR", "quote": "EUR", "rate": 0.01}
        with patch.object(services, "_fetch_json", return_value=rate) as fetch:
            first = services.convert_currency("10000", "inr", "eur")
            self.assertEqual(first["status"], "ok")
            self.assertEqual(first["converted"], "100.00")
            self.assertEqual(first["as_of"], "2026-09-28")
            self.assertIn("time of day is not published", first["as_of_note"])
            self.assertEqual(first["source"], "Frankfurter")
            self.assertEqual(services.convert_currency("20000", "INR", "EUR")["converted"], "200.00")
            fetch.assert_called_once()
        services._cache = services._Cache()
        with patch.object(services, "_fetch_json", side_effect=services.ServiceUnavailable()):
            self.assertEqual(services.convert_currency(100, "INR", "EUR")["status"], "unavailable")
        services._cache.put(("rate", "INR", "EUR"), {"rate": services.Decimal("0.01"),
                            "as_of": "2026-09-28", "retrieved_at_utc": "2026-09-28T10:00:00+00:00"}, -1)
        with patch.object(services, "_fetch_json", side_effect=services.ServiceUnavailable()):
            stale = services.convert_currency(100, "INR", "EUR")
            self.assertTrue(stale["cached"])
            self.assertEqual(stale["as_of"], "2026-09-28")
        self.assertEqual(services.convert_currency(-1, "INR", "EUR")["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
