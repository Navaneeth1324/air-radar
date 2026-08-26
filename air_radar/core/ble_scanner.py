"""
AirRadar Bluetooth Low Energy (BLE) Scanner Engine
Continuously scans for BLE advertisements, calculates real-time RSSI path-loss distance,
and decodes manufacturer data (Apple AirTags, FindMy, Tile, smart wearables, beacons).
"""
import asyncio
import threading
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime

from air_radar.models.device import (
    Device,
    SignalProtocol,
    DeviceCategory,
    BLE_COMPANY_IDENTIFIERS
)
from air_radar.core.distance import calculate_distance_from_rssi, calculate_radar_coordinates

logger = logging.getLogger(__name__)


def classify_ble_device(name: Optional[str], manufacturer_data: Dict[int, bytes]) -> Tuple[str, DeviceCategory, str]:
    """
    Classifies a BLE device into a user-friendly name, category, and vendor.
    """
    dev_name = name or "BLE Peripheral"
    category = DeviceCategory.UNKNOWN
    vendor = "Unknown"

    # Match manufacturer ID
    for company_id, payload in manufacturer_data.items():
        if company_id in BLE_COMPANY_IDENTIFIERS:
            vendor = BLE_COMPANY_IDENTIFIERS[company_id]

        # Apple-specific payload decoding (Company ID 0x004C)
        if company_id == 0x004C and len(payload) > 1:
            apple_type = payload[0]
            if apple_type == 0x12:  # FindMy / AirTag beacon
                dev_name = "Apple FindMy / AirTag Beacon"
                category = DeviceCategory.TRACKER
            elif apple_type == 0x07:  # AirPods / Beats
                dev_name = "Apple AirPods / Beats Audio"
                category = DeviceCategory.AUDIO
            elif apple_type == 0x10:  # Nearby Info / HandOff / Apple Watch
                dev_name = "Apple Device (Nearby)"
                category = DeviceCategory.WEARABLE
            elif apple_type == 0x02:  # iBeacon
                dev_name = "Apple iBeacon"
                category = DeviceCategory.TRACKER

        # Tile Inc. (Company ID 0x01AB)
        elif company_id == 0x01AB:
            dev_name = "Tile Tracking Beacon"
            category = DeviceCategory.TRACKER

        # Samsung (Company ID 0x0075)
        elif company_id == 0x0075:
            if "SmartTag" in dev_name:
                category = DeviceCategory.TRACKER
            elif "Galaxy" in dev_name or "Buds" in dev_name:
                category = DeviceCategory.AUDIO
            else:
                category = DeviceCategory.WEARABLE

    # Name-based classification heuristic
    name_lower = dev_name.lower()
    if any(k in name_lower for k in ["airtag", "findmy", "tile", "beacon", "smarttag", "tag", "chipolo"]):
        category = DeviceCategory.TRACKER
    elif any(k in name_lower for k in ["buds", "headphone", "wh-1000", "bose", "speaker", "audio", "airpods"]):
        category = DeviceCategory.AUDIO
    elif any(k in name_lower for k in ["watch", "band", "fitbit", "garmin", "whoop"]):
        category = DeviceCategory.WEARABLE
    elif any(k in name_lower for k in ["light", "bulb", "hue", "plug", "switch", "sensor"]):
        category = DeviceCategory.SMART_HOME

    return dev_name, category, vendor


class BLEScanner:
    """
    Asynchronous BLE Scanner powered by Bleak running on its own dedicated event loop.
    """
    def __init__(self, on_device_discovered: Callable[[Device], None]):
        self.on_device_discovered = on_device_discovered
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.is_available = True
        self.error_message: Optional[str] = None

    def start(self):
        """Starts the BLE scanning thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_scan())
        except Exception as e:
            logger.warning(f"BLE Scanner loop terminated: {e}")
            self.error_message = str(e)
            self.is_available = False
        finally:
            self._loop.close()

    async def _async_scan(self):
        try:
            from bleak import BleakScanner
        except ImportError:
            self.is_available = False
            self.error_message = "bleak is not installed. Install via `pip install bleak`"
            logger.info(self.error_message)
            return

        def detection_callback(ble_device, advertisement_data):
            try:
                name, category, vendor = classify_ble_device(
                    ble_device.name or advertisement_data.local_name,
                    advertisement_data.manufacturer_data or {}
                )

                rssi = ble_device.rssi or advertisement_data.rssi
                tx_power = advertisement_data.tx_power
                dist_m = calculate_distance_from_rssi(rssi, tx_power)
                angle, _, _ = calculate_radar_coordinates(ble_device.address, distance_m=dist_m, protocol_hint="BLE")

                # Format manufacturer data for inspection
                mfg_dict = {}
                if advertisement_data.manufacturer_data:
                    for cid, raw_b in advertisement_data.manufacturer_data.items():
                        hex_str = raw_b.hex()
                        c_name = BLE_COMPANY_IDENTIFIERS.get(cid, f"0x{cid:04X}")
                        mfg_dict[c_name] = hex_str

                device = Device(
                    id=f"ble:{ble_device.address}",
                    name=name,
                    protocol=SignalProtocol.BLE,
                    vendor=vendor,
                    category=category,
                    rssi=rssi,
                    tx_power=tx_power,
                    estimated_distance_m=dist_m,
                    radar_angle=angle,
                    metadata={
                        "address": ble_device.address,
                        "manufacturer_data": mfg_dict,
                        "service_uuids": list(advertisement_data.service_uuids or []),
                        "local_name": advertisement_data.local_name
                    },
                    first_seen=datetime.now(),
                    last_seen=datetime.now()
                )
                self.on_device_discovered(device)
            except Exception as e:
                logger.debug(f"BLE callback error: {e}")

        try:
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()
            while self._running:
                await asyncio.sleep(1.0)
            await scanner.stop()
        except Exception as e:
            logger.error(f"Bleak scanner error: {e}")
            self.error_message = str(e)
            self.is_available = False

    def stop(self):
        """Stops the BLE scanner."""
        self._running = False
