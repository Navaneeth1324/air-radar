"""
AirRadar Core Engine Orchestrator
Aggregates signal streams from BLE, mDNS, and SSDP discovery engines,
maintains the unified live device registry, runs privacy audits, and dispatches updates.
"""
import time
import math
import random
import threading
import logging
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime

from air_radar.models.device import Device, SignalProtocol, DeviceCategory
from air_radar.core.distance import calculate_radar_coordinates, calculate_distance_from_rssi
from air_radar.core.security import audit_device, calculate_environment_posture
from air_radar.core.mdns_scanner import MDNSScanner
from air_radar.core.ssdp_scanner import SSDPScanner
from air_radar.core.ble_scanner import BLEScanner

logger = logging.getLogger(__name__)


class RadarEngine:
    """
    Central coordinator for AirRadar.
    """
    def __init__(self, enable_ble: bool = True, enable_mdns: bool = True, enable_ssdp: bool = True, demo_mode: bool = False):
        self.enable_ble = enable_ble
        self.enable_mdns = enable_mdns
        self.enable_ssdp = enable_ssdp
        self.demo_mode = demo_mode

        self.devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self._listeners: List[Callable[[Device], None]] = []
        self._running = False
        self._reaper_thread: Optional[threading.Thread] = None
        self._demo_thread: Optional[threading.Thread] = None

        self.ble_scanner: Optional[BLEScanner] = None
        self.mdns_scanner: Optional[MDNSScanner] = None
        self.ssdp_scanner: Optional[SSDPScanner] = None

    def register_listener(self, callback: Callable[[Device], None]):
        """Registers a callback invoked whenever a device is created or updated."""
        self._listeners.append(callback)

    def on_device_discovered(self, new_device: Device):
        """Processes an incoming device advertisement."""
        with self._lock:
            if new_device.id in self.devices:
                existing = self.devices[new_device.id]
                existing.last_seen = datetime.now()
                existing.is_stale = False
                existing.packet_count += 1
                if new_device.rssi is not None:
                    # Smooth RSSI with exponential moving average
                    existing.rssi = int(0.7 * new_device.rssi + 0.3 * (existing.rssi or new_device.rssi))
                    existing.estimated_distance_m = calculate_distance_from_rssi(existing.rssi, existing.tx_power)
                if new_device.name and existing.name.startswith("Unknown"):
                    existing.name = new_device.name
                if new_device.vendor != "Unknown":
                    existing.vendor = new_device.vendor
                if new_device.metadata:
                    existing.metadata.update(new_device.metadata)

                # Re-audit threats
                existing.threats = audit_device(existing)
                device_to_dispatch = existing
            else:
                new_device.threats = audit_device(new_device)
                self.devices[new_device.id] = new_device
                device_to_dispatch = new_device

        for cb in self._listeners:
            try:
                cb(device_to_dispatch)
            except Exception as e:
                logger.debug(f"Error in listener callback: {e}")

    def get_all_devices(self) -> List[Device]:
        """Returns a snapshot copy of all tracked devices."""
        with self._lock:
            return list(self.devices.values())

    def get_posture(self) -> Dict[str, Any]:
        """Calculates current environment security posture."""
        with self._lock:
            dev_list = list(self.devices.values())
        return calculate_environment_posture(dev_list)

    def start(self):
        """Starts all discovery scanners and maintenance routines."""
        if self._running:
            return
        self._running = True

        if self.demo_mode:
            self._start_demo_generator()
            return

        if self.enable_ble:
            self.ble_scanner = BLEScanner(self.on_device_discovered)
            self.ble_scanner.start()

        if self.enable_mdns:
            self.mdns_scanner = MDNSScanner(self.on_device_discovered)
            self.mdns_scanner.start()

        if self.enable_ssdp:
            self.ssdp_scanner = SSDPScanner(self.on_device_discovered)
            self.ssdp_scanner.start()

        # Start background stale-device cleanup thread
        self._reaper_thread = threading.Thread(target=self._reaper_loop, daemon=True)
        self._reaper_thread.start()

    def _reaper_loop(self):
        while self._running:
            time.sleep(10.0)
            now = datetime.now()
            with self._lock:
                for dev in self.devices.values():
                    elapsed = (now - dev.last_seen).total_seconds()
                    if elapsed > 45.0:
                        dev.is_stale = True

    def _start_demo_generator(self):
        """Generates realistic synthetic airwave signals for testing and demonstration."""
        self._demo_thread = threading.Thread(target=self._demo_worker, daemon=True)
        self._demo_thread.start()

    def _demo_worker(self):
        synthetic_devices = [
            ("demo:airtag:01", "Apple AirTag (Backpack)", SignalProtocol.BLE, "Apple, Inc.", DeviceCategory.TRACKER, -52, 1.8),
            ("demo:airtag:02", "Suspicious Unknown Beacon", SignalProtocol.BLE, "Apple, Inc.", DeviceCategory.TRACKER, -45, 1.1),
            ("demo:airpods:01", "AirPods Pro 2", SignalProtocol.BLE, "Apple, Inc.", DeviceCategory.AUDIO, -62, 3.2),
            ("demo:watch:01", "Apple Watch Ultra", SignalProtocol.BLE, "Apple, Inc.", DeviceCategory.WEARABLE, -58, 2.5),
            ("demo:mdns:hue", "Philips Hue Bridge", SignalProtocol.MDNS, "Philips", DeviceCategory.SMART_HOME, -48, 5.0),
            ("demo:mdns:cast", "Living Room TV (Chromecast)", SignalProtocol.MDNS, "Google", DeviceCategory.TV_MEDIA, -55, 6.5),
            ("demo:mdns:spotify", "Sonos Arc (Spotify Connect)", SignalProtocol.MDNS, "Sonos, Inc.", DeviceCategory.AUDIO, -60, 4.2),
            ("demo:ssdp:roku", "Roku Ultra 4K", SignalProtocol.SSDP, "Roku, Inc.", DeviceCategory.TV_MEDIA, -65, 8.0),
            ("demo:ble:esp32", "ESP32 DIY Sensor (Unencrypted)", SignalProtocol.BLE, "Espressif Inc.", DeviceCategory.SMART_HOME, -72, 7.5),
            ("demo:mdns:http", "Insecure Web Cam Admin", SignalProtocol.MDNS, "Generic IP Camera", DeviceCategory.NETWORK, -70, 9.0)
        ]

        # Initial push
        for did, name, proto, vendor, cat, rssi, dist in synthetic_devices:
            angle, _, _ = calculate_radar_coordinates(did, distance_m=dist, protocol_hint=proto.value)
            dev = Device(
                id=did,
                name=name,
                protocol=proto,
                vendor=vendor,
                category=cat,
                rssi=rssi,
                estimated_distance_m=dist,
                radar_angle=angle,
                ip_address=f"192.168.1.{random.randint(10, 200)}" if proto in [SignalProtocol.MDNS, SignalProtocol.SSDP] else None,
                port=80 if "Insecure" in name else 8000,
                service_type="_http._tcp.local." if "Insecure" in name else None,
                metadata={"synthetic": True, "demo_model": "Simulation v1"}
            )
            self.on_device_discovered(dev)

        # Pulse updates periodically
        while self._running:
            time.sleep(2.0)
            target = random.choice(synthetic_devices)
            did = target[0]
            with self._lock:
                if did in self.devices:
                    dev = self.devices[did]
                    # Simulate slight signal fluctuation
                    dev.rssi = max(-95, min(-35, (dev.rssi or -60) + random.randint(-4, 4)))
                    dev.estimated_distance_m = calculate_distance_from_rssi(dev.rssi)
                    dev.last_seen = datetime.now()
                    dev.packet_count += 1
                    dev.threats = audit_device(dev)
                    dev_dispatch = dev
                else:
                    dev_dispatch = None

            if dev_dispatch:
                for cb in self._listeners:
                    cb(dev_dispatch)

    def stop(self):
        """Stops all background scanners cleanly."""
        self._running = False
        if self.ble_scanner:
            self.ble_scanner.stop()
        if self.mdns_scanner:
            self.mdns_scanner.stop()
        if self.ssdp_scanner:
            self.ssdp_scanner.stop()
