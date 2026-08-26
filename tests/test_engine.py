import unittest
import time
from air_radar.core.engine import RadarEngine
from air_radar.models.device import Device, SignalProtocol, DeviceCategory


class TestRadarEngine(unittest.TestCase):
    def test_engine_discovery_and_listeners(self):
        engine = RadarEngine(enable_ble=False, enable_mdns=False, enable_ssdp=False, demo_mode=False)

        received = []
        def on_device(d):
            received.append(d)

        engine.register_listener(on_device)

        dev = Device(
            id="test:device:01",
            name="Test Sensor",
            protocol=SignalProtocol.BLE,
            category=DeviceCategory.SMART_HOME,
            rssi=-55
        )
        engine.on_device_discovered(dev)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].id, "test:device:01")
        self.assertEqual(len(engine.get_all_devices()), 1)

    def test_engine_demo_mode(self):
        engine = RadarEngine(demo_mode=True)
        engine.start()
        time.sleep(0.5)

        devices = engine.get_all_devices()
        self.assertGreater(len(devices), 0)

        posture = engine.get_posture()
        self.assertGreater(posture["total_devices"], 0)
        engine.stop()


if __name__ == "__main__":
    unittest.main()
