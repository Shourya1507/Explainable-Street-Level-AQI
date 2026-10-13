"""
Tests for backend/data_pipeline/build_features.py

Covers:
  - haversine_km distance computation
  - time_features extraction (temporal flags)
  - compute_road_density (IDW interpolation from Delhi nodes)
  - build_neighbor_features (leakage check, IDW, spread)

build_features.py has top-level imports of boto3, pandas and requests which are
not installed in the lightweight CI environment.  All test classes are skipped
gracefully when those packages are absent; the pure-math functions are extracted
and tested directly so they always run.
"""

import unittest
import sys
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "data_pipeline"))

# ── Attempt to import build_features; skip all tests if heavy deps absent ──
try:
    import build_features as bf
    BF_AVAILABLE = True
    BF_SKIP_REASON = ""
except (ImportError, SystemExit) as _e:
    BF_AVAILABLE = False
    BF_SKIP_REASON = f"build_features dependencies not installed ({_e})"
    bf = None  # type: ignore


# ---------------------------------------------------------------------------
# Inline pure-math helpers — identical to the real implementations in
# build_features.py.  These run in CI even when boto3/pandas are absent.
# ---------------------------------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _time_features(dt):
    return {
        "hour_of_day":     dt.hour,
        "day_of_week":     dt.weekday(),
        "month":           dt.month,
        "is_weekend":      int(dt.weekday() >= 5),
        "is_morning_peak": int(dt.hour in (7, 8, 9, 10)),
        "is_evening_peak": int(dt.hour in (17, 18, 19, 20)),
    }


# ── haversine distance (always runs) ──────────────────────────────────────

class TestHaversineKm(unittest.TestCase):

    def _fn(self, lat1, lon1, lat2, lon2):
        # Use the real function when available, otherwise the inline copy
        if BF_AVAILABLE:
            return bf.haversine_km(lat1, lon1, lat2, lon2)
        return _haversine_km(lat1, lon1, lat2, lon2)

    def test_same_point_is_zero(self):
        self.assertAlmostEqual(self._fn(28.6139, 77.2090, 28.6139, 77.2090), 0.0, places=6)

    def test_known_delhi_distance(self):
        # India Gate → Connaught Place ≈ 2.2 km straight-line
        d = self._fn(28.6129, 77.2295, 28.6304, 77.2177)
        self.assertGreater(d, 1.5)
        self.assertLess(d, 3.0)

    def test_symmetry(self):
        d1 = self._fn(28.63, 77.21, 28.55, 77.10)
        d2 = self._fn(28.55, 77.10, 28.63, 77.21)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_result_is_positive(self):
        self.assertGreater(self._fn(28.0, 77.0, 29.0, 78.0), 0)

    def test_delhi_to_mumbai_roughly_1150km(self):
        d = self._fn(28.6, 77.2, 19.08, 72.88)
        self.assertGreater(d, 1050)
        self.assertLess(d, 1300)


# ── time_features (always runs) ───────────────────────────────────────────

class TestTimeFeatures(unittest.TestCase):

    def _fn(self, dt):
        if BF_AVAILABLE:
            return bf.time_features(dt)
        return _time_features(dt)

    def test_morning_peak_at_8am(self):
        feats = self._fn(datetime(2026, 10, 7, 8, 0, 0))
        self.assertEqual(feats["is_morning_peak"], 1)
        self.assertEqual(feats["is_evening_peak"], 0)

    def test_evening_peak_at_18(self):
        feats = self._fn(datetime(2026, 10, 7, 18, 0, 0))
        self.assertEqual(feats["is_evening_peak"], 1)
        self.assertEqual(feats["is_morning_peak"], 0)

    def test_midday_not_a_peak(self):
        feats = self._fn(datetime(2026, 10, 7, 13, 0, 0))
        self.assertEqual(feats["is_morning_peak"], 0)
        self.assertEqual(feats["is_evening_peak"], 0)

    def test_weekend_flag_saturday(self):
        feats = self._fn(datetime(2026, 10, 10, 10, 0, 0))  # Saturday
        self.assertEqual(feats["is_weekend"], 1)

    def test_weekday_flag_monday(self):
        feats = self._fn(datetime(2026, 10, 12, 8, 0, 0))  # Monday
        self.assertEqual(feats["is_weekend"], 0)

    def test_month_field(self):
        feats = self._fn(datetime(2026, 5, 1, 6, 0, 0))
        self.assertEqual(feats["month"], 5)

    def test_hour_of_day(self):
        feats = self._fn(datetime(2026, 10, 7, 15, 0, 0))
        self.assertEqual(feats["hour_of_day"], 15)

    def test_all_keys_present(self):
        feats = self._fn(datetime(2026, 10, 7, 12, 0, 0))
        for key in ("hour_of_day", "day_of_week", "month",
                    "is_weekend", "is_morning_peak", "is_evening_peak"):
            self.assertIn(key, feats, f"Missing key: {key}")


# ── Tests that need the real build_features module (skip in CI if absent) ─

@unittest.skipUnless(BF_AVAILABLE, BF_SKIP_REASON or "build_features unavailable")
class TestRoadDensity(unittest.TestCase):

    def test_returns_float(self):
        d = bf.compute_road_density(28.6304, 77.2177)
        self.assertIsInstance(d, float)

    def test_connaught_place_high_density(self):
        d = bf.compute_road_density(28.6304, 77.2177)
        self.assertGreater(d, 12.0)

    def test_rural_south_low_density(self):
        d = bf.compute_road_density(28.4680, 77.2450)
        self.assertLess(d, 8.0)

    def test_within_valid_bounds(self):
        for lat, lon in [(28.6304, 77.2177), (28.7041, 77.1025), (28.4680, 77.2450)]:
            d = bf.compute_road_density(lat, lon)
            self.assertGreaterEqual(d, 1.5, f"Too low at ({lat},{lon})")
            self.assertLessEqual(d, 20.0,  f"Too high at ({lat},{lon})")


@unittest.skipUnless(BF_AVAILABLE, BF_SKIP_REASON or "build_features unavailable")
class TestBuildNeighborFeatures(unittest.TestCase):

    COORDS = {
        "in-cpcb-cp":     (28.6304, 77.2177),
        "in-cpcb-igi":    (28.5562, 77.1000),
        "in-cpcb-rohini": (28.7041, 77.1025),
        "in-cpcb-anand":  (28.6469, 77.3160),
        "in-cpcb-lodhi":  (28.5921, 77.2232),
        "in-cpcb-dwarka": (28.5921, 77.0460),
    }
    PM25 = {
        "in-cpcb-cp":     120.0,
        "in-cpcb-igi":    100.0,
        "in-cpcb-rohini": 145.0,
        "in-cpcb-anand":  130.0,
        "in-cpcb-lodhi":  115.0,
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
        self.assertGreaterEqual(result["nearby_station_idw"], 90.0)
        self.assertLessEqual(result["nearby_station_idw"], 160.0)

    def test_no_nan_with_valid_inputs(self):
        result = self._call("in-cpcb-cp", 28.6304, 77.2177)
        for key, val in result.items():
            self.assertFalse(math.isnan(float(val)), f"NaN in {key}")


if __name__ == "__main__":
    unittest.main()
