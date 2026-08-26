"""
AirRadar Data Models
Defines core data structures for discovered wireless and network devices.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class SignalProtocol(str, Enum):
    BLE = "BLE"
    MDNS = "mDNS"
    SSDP = "SSDP"
    LAN = "LAN"
    SYNTHETIC = "DEMO"


class DeviceCategory(str, Enum):
    TRACKER = "tracker"           # AirTags, Tiles, Beacons
    AUDIO = "audio"               # AirPods, Smart Speakers, AirPlay, Spotify
    SMART_HOME = "smart_home"     # Hue, smart plugs, thermostats
    TV_MEDIA = "tv_media"         # Smart TVs, Apple TV, Chromecast
    WEARABLE = "wearable"         # Apple Watch, Fitbit, smart bands
    NETWORK = "network"           # Routers, APs, Gateways
    COMPUTER_PHONE = "computer"   # MacBooks, iPhones, PCs
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    INFO = "INFO"
    WARN = "WARN"
    ALERT = "ALERT"


@dataclass
class ThreatIndicator:
    level: RiskLevel
    title: str
    description: str
    remediation: Optional[str] = None


@dataclass
class Device:
    id: str  # Unique MAC, UUID, or synthetic ID
    name: str
    protocol: SignalProtocol
    vendor: str = "Unknown"
    category: DeviceCategory = DeviceCategory.UNKNOWN
    rssi: Optional[int] = None  # Signal strength in dBm (-100 to -20)
    tx_power: Optional[int] = None
    estimated_distance_m: Optional[float] = None
    radar_angle: float = 0.0  # Angle in radians (0 to 2*PI)
    ip_address: Optional[str] = None
    port: Optional[int] = None
    service_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    threats: List[ThreatIndicator] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    is_stale: bool = False
    packet_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the device object to a dictionary for JSON/WebSocket streaming."""
        return {
            "id": self.id,
            "name": self.name,
            "protocol": self.protocol.value,
            "vendor": self.vendor,
            "category": self.category.value,
            "rssi": self.rssi,
            "estimated_distance_m": round(self.estimated_distance_m, 2) if self.estimated_distance_m is not None else None,
            "radar_angle": round(self.radar_angle, 4),
            "ip_address": self.ip_address,
            "port": self.port,
            "service_type": self.service_type,
            "metadata": self.metadata,
            "threats": [
                {
                    "level": t.level.value,
                    "title": t.title,
                    "description": t.description,
                    "remediation": t.remediation
                }
                for t in self.threats
            ],
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "is_stale": self.is_stale,
            "packet_count": self.packet_count
        }


# Common BLE Vendor OUI / Manufacturer Company IDs
BLE_COMPANY_IDENTIFIERS: Dict[int, str] = {
    0x004C: "Apple, Inc.",
    0x0075: "Samsung Electronics",
    0x0006: "Microsoft",
    0x00E0: "Google",
    0x01AB: "Tile, Inc.",
    0x0059: "Nordic Semiconductor",
    0x02E5: "Espressif Inc.",
    0x0087: "Garmin International",
    0x0157: "Anker Innovations",
    0x000A: "Qualcomm",
    0x000F: "Broadcom",
    0x01D3: "Sonos, Inc.",
    0x00D2: "Dialog Semiconductor",
    0x038F: "Xiaomi Inc.",
    0x0047: "Sony Corporation",
    0x0001: "Nokia Mobile Phones",
    0x0002: "Intel Corp.",
    0x0003: "IBM Corp.",
    0x0004: "Toshiba Corp.",
    0x0005: "3Com",
    0x008C: "Logitech International",
    0x00B5: "Bose Corporation"
}

# MAC Prefix to Vendor lookup
MAC_OUI_LOOKUP: Dict[str, str] = {
    "00:1A:11": "Google",
    "00:17:88": "Philips Lighting (Hue)",
    "F0:99:B6": "Apple, Inc.",
    "AC:BC:32": "Apple, Inc.",
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Foundation",
    "50:02:91": "Amazon Technologies",
    "FC:65:DE": "Amazon Technologies",
    "24:0A:C4": "Espressif (ESP32/ESP8266)",
    "30:AE:A4": "Espressif (ESP32/ESP8266)",
    "D8:96:E0": "Tesla, Inc.",
    "00:04:20": "Cisco Systems",
    "00:11:32": "Synology Inc."
}
