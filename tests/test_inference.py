import unittest
try:
    import numpy as np
except ImportError:
    np = None

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "lambda" / "estimate"))

from lambda_inference import FEATURE_COLS, DRIVER_NOTES


class TestLambdaInference(unittest.TestCase):

    def test_feature_cols_count(self):
        # Must be exactly 17 features
        self.assertEqual(len(FEATURE_COLS), 17)
        self.assertIn("nearby_station_avg", FEATURE_COLS)
        self.assertIn("nearby_station_idw", FEATURE_COLS)
        self.assertIn("neighbor_spread", FEATURE_COLS)
        self.assertIn("nearest_station_km", FEATURE_COLS)
        self.assertIn("road_density", FEATURE_COLS)
        self.assertIn("hour_of_day", FEATURE_COLS)

    def test_driver_notes_coverage(self):
        # All feature columns should have human-readable notes
        for col in FEATURE_COLS:
            self.assertIn(col, DRIVER_NOTES, f"Missing driver note for feature: {col}")

    def test_feature_array_generation(self):
        if np is None:
            self.skipTest("numpy not installed in local environment")
        sample_features = {
            "nearby_station_avg": 120.0,
            "nearby_station_idw": 115.0,
            "neighbor_spread": 10.5,
            "nearest_station_km": 2.4,
            "temperature": 28.5,
            "humidity": 60.0,
            "wind_speed": 1.8,
            "wind_direction": 270.0,
            "surface_pressure": 1012.0,
            "boundary_layer": 450.0,
            "road_density": 14.2,
            "hour_of_day": 18,
            "day_of_week": 4,
            "month": 10,
            "is_weekend": 0,
            "is_morning_peak": 0,
            "is_evening_peak": 1,
        }
        row = np.array(
            [sample_features.get(col, float("nan")) for col in FEATURE_COLS],
            dtype=np.float32,
        ).reshape(1, -1)
        self.assertEqual(row.shape, (1, 17))
        self.assertFalse(np.isnan(row).any())


if __name__ == "__main__":
    unittest.main()
