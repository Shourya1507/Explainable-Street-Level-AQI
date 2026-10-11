import unittest
from datetime import datetime, timezone, timedelta

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "lambda" / "estimate"))

from handler import time_features, IST_OFFSET


class TestTimeFeatures(unittest.TestCase):

    def test_ist_offset(self):
        self.assertEqual(IST_OFFSET, timedelta(hours=5, minutes=30))

    def test_morning_peak(self):
        # 8:30 AM IST on Wednesday (weekday)
        dt_ist = datetime(2026, 10, 14, 8, 30, tzinfo=timezone(IST_OFFSET))
        feats = time_features(dt_ist)
        self.assertEqual(feats["hour_of_day"], 8)
        self.assertEqual(feats["is_morning_peak"], 1)
        self.assertEqual(feats["is_evening_peak"], 0)
        self.assertEqual(feats["is_weekend"], 0)

    def test_evening_peak(self):
        # 6:45 PM (18:45) IST on Friday
        dt_ist = datetime(2026, 10, 16, 18, 45, tzinfo=timezone(IST_OFFSET))
        feats = time_features(dt_ist)
        self.assertEqual(feats["hour_of_day"], 18)
        self.assertEqual(feats["is_morning_peak"], 0)
        self.assertEqual(feats["is_evening_peak"], 1)
        self.assertEqual(feats["is_weekend"], 0)

    def test_weekend(self):
        # Sunday 2:00 PM IST
        dt_ist = datetime(2026, 10, 18, 14, 0, tzinfo=timezone(IST_OFFSET))
        feats = time_features(dt_ist)
        self.assertEqual(feats["is_weekend"], 1)
        self.assertEqual(feats["is_morning_peak"], 0)
        self.assertEqual(feats["is_evening_peak"], 0)


if __name__ == "__main__":
    unittest.main()
