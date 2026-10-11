import json
import unittest
from datetime import datetime, timezone

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "lambda" / "estimate"))

from handler import handler


class TestHandlerValidation(unittest.TestCase):

    def test_missing_coordinates(self):
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"timestamp": "2026-10-11T14:00:00Z"}),
        }
        resp = handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        body = json.loads(resp["body"])
        self.assertEqual(body.get("error"), "MISSING_PARAMETERS")

    def test_out_of_bounds_coordinates(self):
        # Mumbai coordinates
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"lat": 19.0760, "lon": 72.8777}),
        }
        resp = handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        body = json.loads(resp["body"])
        self.assertEqual(body.get("error"), "OUT_OF_BOUNDS")

    def test_invalid_timestamp(self):
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"lat": 28.6139, "lon": 77.2090, "timestamp": "invalid-time"}),
        }
        resp = handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        body = json.loads(resp["body"])
        self.assertEqual(body.get("error"), "INVALID_TIMESTAMP")

    def test_valid_delhi_coordinates_mock_mode(self):
        # Connaught Place in Delhi
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"lat": 28.6304, "lon": 77.2177, "timestamp": "2026-10-11T14:00:00Z"}),
        }
        resp = handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertIn("pm25", body)
        self.assertEqual(body["lat"], 28.6304)
        self.assertEqual(body["lon"], 77.2177)

    def test_cors_options(self):
        event = {"httpMethod": "OPTIONS"}
        resp = handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertIn("Access-Control-Allow-Origin", resp["headers"])


if __name__ == "__main__":
    unittest.main()
