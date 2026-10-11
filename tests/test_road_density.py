import unittest

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "lambda" / "estimate"))

from handler import road_density_for


class TestRoadDensity(unittest.TestCase):

    def test_central_delhi_density(self):
        # Connaught Place (central urban core)
        cp_density = road_density_for(28.6304, 77.2177)
        self.assertGreater(cp_density, 12.0)
        self.assertLessEqual(cp_density, 20.0)

    def test_outer_ridge_density(self):
        # Asola Bhatti / Southern Ridge (rural / forest fringe)
        ridge_density = road_density_for(28.4680, 77.2450)
        self.assertLess(ridge_density, 6.0)
        self.assertGreaterEqual(ridge_density, 1.5)

    def test_density_bounds(self):
        # Random Delhi coordinates must stay within realistic physical bounds
        test_coords = [
            (28.6139, 77.2090),  # India Gate
            (28.7041, 77.1025),  # Pitampura
            (28.5355, 77.2732),  # Okhla
            (28.8530, 77.0930),  # Narela
        ]
        for lat, lon in test_coords:
            d = road_density_for(lat, lon)
            self.assertGreaterEqual(d, 1.5)
            self.assertLessEqual(d, 20.0)


if __name__ == "__main__":
    unittest.main()
