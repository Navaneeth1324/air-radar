import unittest
import math
from air_radar.core.distance import calculate_distance_from_rssi, calculate_radar_coordinates


class TestDistanceAlgorithms(unittest.TestCase):
    def test_rssi_distance_calculation(self):
        # At reference RSSI (-59 dBm), distance should be ~1.0m
        dist_1m = calculate_distance_from_rssi(-59, tx_power=-59)
        self.assertIsNotNone(dist_1m)
        self.assertTrue(0.9 <= dist_1m <= 1.1)

        # Stronger signal (-40 dBm) should be closer (< 1.0m)
        dist_close = calculate_distance_from_rssi(-40, tx_power=-59)
        self.assertIsNotNone(dist_close)
        self.assertLess(dist_close, 1.0)

        # Weaker signal (-80 dBm) should be further (> 1.0m)
        dist_far = calculate_distance_from_rssi(-80, tx_power=-59)
        self.assertIsNotNone(dist_far)
        self.assertGreater(dist_far, 1.0)

        # None or 0 RSSI should return None
        self.assertIsNone(calculate_distance_from_rssi(None))
        self.assertIsNone(calculate_distance_from_rssi(0))

    def test_deterministic_polar_coordinates(self):
        dev_id = "apple:airtag:fa:23:45"
        angle1, radius1, dist1 = calculate_radar_coordinates(dev_id, distance_m=2.5)
        angle2, radius2, dist2 = calculate_radar_coordinates(dev_id, distance_m=2.5)

        # Coordinates must be completely deterministic for the same device ID
        self.assertEqual(angle1, angle2)
        self.assertEqual(radius1, radius2)
        self.assertEqual(dist1, dist2)
        self.assertTrue(0 <= angle1 <= 2 * math.pi)
        self.assertTrue(0.08 <= radius1 <= 1.0)


if __name__ == "__main__":
    unittest.main()
