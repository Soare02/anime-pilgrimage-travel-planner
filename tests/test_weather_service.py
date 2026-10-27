import unittest
from unittest.mock import Mock, patch

from weather_service import fetch_weather_snapshot


class WeatherServiceTests(unittest.TestCase):
    def test_coordinate_query_keeps_real_forecast_dates_and_rain_chances(self):
        response = Mock()
        response.json.return_value = {
            "nearest_area": [{"areaName": [{"value": "Uji"}]}],
            "current_condition": [{"temp_C": "18", "weatherDesc": [{"value": "Cloudy"}]}],
            "weather": [{
                "date": "2026-10-27", "mintempC": "12", "maxtempC": "20",
                "astronomy": [{"sunrise": "06:12 AM", "sunset": "05:10 PM"}],
                "hourly": [
                    {"time": "600", "lang_zh": [{"value": "小雨"}], "chanceofrain": "45", "tempC": "15"},
                    {"time": "1500", "lang_zh": [{"value": "晴"}], "chanceofrain": "90", "tempC": "20"},
                ],
            }, {"date": "bad date", "hourly": []}],
        }
        with patch("weather_service.requests.get", return_value=response) as get:
            result = fetch_weather_snapshot([34.89, 135.8])
        self.assertEqual(get.call_args.args[0], "https://wttr.in/34.8900,135.8000")
        self.assertEqual(get.call_args.kwargs["params"]["format"], "j1")
        self.assertEqual(result.location, "Uji")
        self.assertIn("18°C", result.current_summary)
        self.assertEqual(len(result.forecast), 1)
        self.assertEqual(result.forecast[0].date.isoformat(), "2026-10-27")
        self.assertEqual(result.forecast[0].rain_chance_percent, 90)
        self.assertEqual(result.forecast[0].summary, "小雨 / 晴")
        self.assertEqual(result.forecast[0].min_temp_c, 12)
        self.assertEqual([hour.time for hour in result.forecast[0].hourly], ["06:00", "15:00"])
        self.assertEqual(result.forecast[0].hourly[0].rain_chance_percent, 45)
        self.assertEqual(result.forecast[0].sunrise, "06:12")
        self.assertEqual(result.forecast[0].sunset, "17:10")
        self.assertTrue(result.retrieved_at)

    def test_current_weather_is_not_copied_into_forecast(self):
        response = Mock()
        response.json.return_value = {"current_condition": [{"temp_C": "20", "weatherDesc": [{"value": "Sunny"}]}]}
        with patch("weather_service.requests.get", return_value=response):
            result = fetch_weather_snapshot([35, 135])
        self.assertIn("Sunny", result.current_summary)
        self.assertEqual(result.forecast, [])

    def test_empty_or_non_json_weather_is_not_treated_as_success(self):
        for payload in ({}, [], {"weather": [{"date": "invalid"}]}):
            response = Mock()
            response.json.return_value = payload
            with self.subTest(payload=payload), patch("weather_service.requests.get", return_value=response):
                with self.assertRaises(ValueError):
                    fetch_weather_snapshot([35, 135])


if __name__ == "__main__":
    unittest.main()
