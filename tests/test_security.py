import unittest
from air_radar.models.device import Device, SignalProtocol, DeviceCategory, RiskLevel
from air_radar.core.security import audit_device, calculate_environment_posture


class TestSecurityEngine(unittest.TestCase):
    def test_cleartext_http_audit(self):
        dev = Device(
            id="mdns:192.168.1.50:80",
            name="Insecure Router Web Admin",
            protocol=SignalProtocol.MDNS,
            service_type="_http._tcp.local.",
            port=80
        )
        threats = audit_device(dev)
        self.assertGreaterEqual(len(threats), 1)
        self.assertTrue(any(t.level == RiskLevel.WARN for t in threats))

    def test_airtag_proximity_alert(self):
        dev = Device(
            id="ble:airtag:99",
            name="Apple AirTag",
            protocol=SignalProtocol.BLE,
            category=DeviceCategory.TRACKER,
            rssi=-50  # Strong signal = close proximity
        )
        threats = audit_device(dev)
        self.assertGreaterEqual(len(threats), 1)
        self.assertTrue(any(t.level == RiskLevel.ALERT for t in threats))

    def test_environment_posture_calculation(self):
        safe_dev = Device(
            id="ble:headphones:01",
            name="Wireless Headphones",
            protocol=SignalProtocol.BLE,
            category=DeviceCategory.AUDIO,
            rssi=-65
        )
        threat_dev = Device(
            id="ble:tracker:02",
            name="AirTag Tracker",
            protocol=SignalProtocol.BLE,
            category=DeviceCategory.TRACKER,
            rssi=-48
        )
        threat_dev.threats = audit_device(threat_dev)

        posture = calculate_environment_posture([safe_dev, threat_dev])
        self.assertEqual(posture["total_devices"], 2)
        self.assertEqual(posture["tracker_count"], 1)
        self.assertLess(posture["score"], 100)


if __name__ == "__main__":
    unittest.main()
