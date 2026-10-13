"""
Tests for backend/data_pipeline/build_features.py

Covers:
  - haversine_km distance computation
  - time_features extraction (temporal flags, IST-aware hour)
  - compute_road_density (IDW interpolation from Delhi nodes)
  - build_neighbor_features (leakage check, IDW, spread)
"""

import unittest
import sys
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "data_pipeline"))

import build_features as bf


# ── haversine_km ──────────────────────────────────────────────────────────

class TestHaversineKm(unittest.TestCase):

    def test_same_point_is_zero(self):
        d = bf.haversine_km(28.6139, 77.2090, 28.6139, 77.2090)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_known_delhi_distance(self):
        # India Gate → Connaught Place ≈ 2.2 km straight-line
        d = bf.haversine_km(28.6129, 77.2295, 28.6304, 77.2177)
        self.assertGreater(d, 1.5)
        self.assertLess(d, 3.0)

    def test_symmetry(self):
        d1 = bf.haversine_km(28.63, 77.21, 28.55, 77.10)
        d2 = bf.haversine_km(28.55, 77.10, 28.63, 77.21)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_result_is_positive(self):
        d = bf.haversine_km(28.0, 77.0, 29.0, 78.0)
        self.assertGreater(d, 0)

    def test_delhi_to_mumbai_roughly_1150km(self):
        d = bf.haversine_km(28.6, 77.2, 19.08, 72.88)
        self.assertGreater(d, 1050)
        self.assertLess(d, 1300)


# ── time_features ─────────────────────────────────────────────────────────

class TestTimeFeatures(unittest.TestCase):
    """
    build_features.time_features(dt) → dict with:
      hour_of_day, day_of_week, month, is_weekend, is_morning_peak, is_evening_peak
    The datetime is consumed as-is (caller should convert to IST first).
    """

    def test_morning_peak_at_8am(self):
        dt = datetime(2026, 10, 7, 8, 0, 0)  # Wednesday 08:00
        feats = bf.time_features(dt)
        self.assertEqual(feats["is_morning_peak"], 1)
        self.assertEqual(feats["is_evening_peak"], 0)

    def test_evening_peak_at_18(self):
        dt = datetime(2026, 10, 7, 18, 0, 0)  # Wednesday 18:00
        feats = bf.time_features(dt)
        self.assertEqual(feats["is_evening_peak"], 1)
        self.assertEqual(feats["is_morning_peak"], 0)

    def test_midday_not_a_peak(self):
        dt = datetime(2026, 10, 7, 13, 0, 0)
        feats = bf.time_features(dt)
        self.assertEqual(feats["is_morning_peak"], 0)
        self.assertEqual(feats["is_evening_peak"], 0)

    def test_weekend_flag_saturday(self):
        # weekday() == 5 for Saturday
        dt = datetime(2026, 10, 10, 10, 0, 0)  # Saturday
        feats = bf.time_features(dt)
        self.assertEqual(feats["is_weekend"], 1)

    def test_weekday_flag_monday(self):
        dt = datetime(2026, 10, 12, 8, 0, 0)  # Monday
        feats = bf.time_features(dt)
        self.assertEqual(feats["is_weekend"], 0)

    def test_month_field(self):
        dt = datetime(2026, 5, 1, 6, 0, 0)
        feats = bf.time_features(dt)
        self.assertEqual(feats["month"], 5)

    def test_hour_of_day(self):
        dt = datetime(2026, 10, 7, 15, 0, 0)
        feats = bf.time_features(dt)
        self.assertEqual(feats["hour_of_day"], 15)

    def test_all_keys_present(self):
        dt = datetime(2026, 10, 7, 12, 0, 0)
        feats = bf.time_features(dt)
        for key in ("hour_of_day", "day_of_week", "month",
                    "is_weekend", "is_morning_peak", "is_evening_peak"):
            self.assertIn(key, feats, f"Missing key: {key}")


# ── compute_road_density ──────────────────────────────────────────────────

class TestRoadDensity(unittest.TestCase):

    def test_returns_float(self):
        d = bf.compute_road_density(28.6304, 77.2177)
        self.assertIsInstance(d, float)

    def test_connaught_place_high_density(self):
        # CP is a known high-density node (16.5 km/km²)
        d = bf.compute_road_density(28.6304, 77.2177)
        self.assertGreater(d, 12.0)

    def test_rural_south_low_density(self):
        # Asola Bhatti / Southern Ridge ≈ 2.1
        d = bf.compute_road_density(28.4680, 77.2450)
        self.assertLess(d, 8.0)

    def test_within_valid_bounds(self):
        # compute_road_density clamps to [1.5, 20.0]
        for lat, lon in [(28.6304, 77.2177), (28.7041, 77.1025), (28.4680, 77.2450)]:
            d = bf.compute_road_density(lat, lon)
            self.assertGreaterEqual(d, 1.5, f"Too low at ({lat},{lon})")
            self.assertLessEqual(d, 20.0, f"Too high at ({lat},{lon})")


# ── build_neighbor_features ───────────────────────────────────────────────

class TestBuildNeighborFeatures(unittest.TestCase):

    # Minimal synthetic Delhi station set
    COORDS = {
        "in-cpcb-cp":      (28.6304, 77.2177),
        "in-cpcb-igi":     (28.5562, 77.1000),
        "in-cpcb-rohini":  (28.7041, 77.1025),
        "in-cpcb-anand":   (28.6469, 77.3160),
        "in-cpcb-lodhi":   (28.5921, 77.2232),
        "in-cpcb-dwarka":  (28.5921, 77.0460),
    }
    PM25 = {
        "in-cpcb-cp":      120.0,
        "in-cpcb-igi":     100.0,
        "in-cpcb-rohini":  145.0,
        "in-cpcb-anand":   130.0,
        "in-cpcb-lodhi":   115.0,
        "in-cpcb-dwarka":  95.0,
    }

    def _call(self, target_id, lat, lon):
        return bf.build_neighbor_features(
            station_id=target_id,
            hour_dt=datetime(2026, 10, 7, 14, 0, 0),
            all_stations_pm25=self.PM25,
            all_stations_coords=self.COORDS,
            target_lat=lat,
            target_lon=lon,
        )

    def test_returns_expected_keys(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        for key in ("nearest_station_km", "nearby_station_avg",
                    "nearby_station_idw", "neighbor_spread"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_leakage_guard_target_excluded(self):
        # When computing neighbors for CP, CP's own reading must NOT appear
        # (verified indirectly: nearby_station_avg != 120.0 if others avg correctly)
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        self.assertNotAlmostEqual(result["nearby_station_avg"], 120.0, places=0)

    def test_nearest_km_is_positive(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        self.assertGreater(result["nearest_station_km"], 0)

    def test_spread_non_negative(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        self.assertGreaterEqual(result["neighbor_spread"], 0)

    def test_idw_between_min_and_max_of_neighbors(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        # IDW should be within the range of actual neighbor readings
        self.assertGreaterEqual(result["nearby_station_idw"], 90.0)
        self.assertLessEqual(result["nearby_station_idw"], 160.0)

    def test_no_nan_with_valid_inputs(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        for key, val in result.items():
            self.assertFalse(math.isnan(float(val)), f"NaN in {key}")


if __name__ == "__main__":
    unittest.main()
