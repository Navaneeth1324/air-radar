"""
AirRadar mDNS / Bonjour ZeroConf Discovery Engine
Discovers local network broadcasts (AirPlay, Chromecast, Spotify, Smart Home, HTTP/HTTPS).
Supports native zeroconf package as well as pure-Python socket multicast fallback.
"""
import socket
import struct
import threading
import time
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime

from air_radar.models.device import Device, SignalProtocol, DeviceCategory
from air_radar.core.distance import calculate_radar_coordinates

logger = logging.getLogger(__name__)

# Common ZeroConf service names mapped to categories and friendly labels
KNOWN_MDNS_SERVICES = {
    "_airplay._tcp.local.": ("Apple AirPlay", DeviceCategory.TV_MEDIA, "Apple, Inc."),
    "_raop._tcp.local.": ("AirPlay Audio (RAOP)", DeviceCategory.AUDIO, "Apple, Inc."),
    "_googlecast._tcp.local.": ("Google Cast", DeviceCategory.TV_MEDIA, "Google"),
    "_spotify-connect._tcp.local.": ("Spotify Connect", DeviceCategory.AUDIO, "Spotify"),
    "_sonos._tcp.local.": ("Sonos Speaker", DeviceCategory.AUDIO, "Sonos, Inc."),
    "_hue._tcp.local.": ("Philips Hue Bridge", DeviceCategory.SMART_HOME, "Philips"),
    "_homekit._tcp.local.": ("Apple HomeKit Accessory", DeviceCategory.SMART_HOME, "Apple, Inc."),
    "_hap._tcp.local.": ("HomeKit Accessory Protocol", DeviceCategory.SMART_HOME, "Apple, Inc."),
    "_ipp._tcp.local.": ("Network Printer (IPP)", DeviceCategory.NETWORK, "Network Printer"),
    "_http._tcp.local.": ("Web Server (HTTP)", DeviceCategory.NETWORK, "Web Server"),
    "_https._tcp.local.": ("Secure Web Server (HTTPS)", DeviceCategory.NETWORK, "Web Server"),
    "_ssh._tcp.local.": ("SSH Server", DeviceCategory.COMPUTER_PHONE, "SSH Host"),
    "_smb._tcp.local.": ("SMB File Share", DeviceCategory.COMPUTER_PHONE, "Samba / Windows Share"),
    "_companion-link._tcp.local.": ("Apple Companion Link", DeviceCategory.COMPUTER_PHONE, "Apple, Inc.")
}


class MDNSScanner:
    """
    Multicast DNS scanner. Uses `zeroconf` if available, otherwise runs
    a lightweight UDP multicast socket listener on 224.0.0.251:5353.
    """
    def __init__(self, on_device_discovered: Callable[[Device], None]):
        self.on_device_discovered = on_device_discovered
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._zeroconf_browser = None
        self._zeroconf = None

    def start(self):
        """Starts passive mDNS listening in a background thread."""
        if self._running:
            return
        self._running = True

        try:
            import zeroconf
            self._start_zeroconf()
        except ImportError:
            logger.info("zeroconf package not found; falling back to native UDP multicast listener.")
            self._start_native_multicast()

    def _start_zeroconf(self):
        """Uses the official Zeroconf library for deep record inspection."""
        from zeroconf import Zeroconf, ServiceBrowser

        class ServiceListener:
            def __init__(self, outer):
                self.outer = outer

            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if not info:
                    return

                addresses = [socket.inet_ntoa(addr) for addr in info.addresses if len(addr) == 4]
                ip_str = addresses[0] if addresses else "unknown"
                port = info.port

                friendly_name, category, vendor = KNOWN_MDNS_SERVICES.get(
                    type_,
                    (name.split(".")[0], DeviceCategory.NETWORK, "Unknown")
                )

                dev_id = f"mdns:{ip_str}:{port}"
                angle, _, dist = calculate_radar_coordinates(dev_id, protocol_hint="mDNS")

                meta: Dict[str, Any] = {
                    "server": info.server,
                    "service_type": type_,
                    "properties": {k.decode("utf-8", "replace"): v.decode("utf-8", "replace") if isinstance(v, bytes) else v for k, v in (info.properties or {}).items()}
                }

                device = Device(
                    id=dev_id,
                    name=name.split(".")[0] or friendly_name,
                    protocol=SignalProtocol.MDNS,
                    vendor=vendor,
                    category=category,
                    rssi=-55,  # Nominal LAN strength
                    estimated_distance_m=dist,
                    radar_angle=angle,
                    ip_address=ip_str,
                    port=port,
                    service_type=type_,
                    metadata=meta,
                    first_seen=datetime.now(),
                    last_seen=datetime.now()
                )
                self.outer.on_device_discovered(device)

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.add_service(zc, type_, name)

        self._zeroconf = Zeroconf()
        types_to_browse = list(KNOWN_MDNS_SERVICES.keys())
        self._zeroconf_browser = ServiceBrowser(self._zeroconf, types_to_browse, ServiceListener(self))

    def _start_native_multicast(self):
        """Native socket listener listening to 224.0.0.251:5353."""
        self._thread = threading.Thread(target=self._multicast_worker, daemon=True)
        self._thread.start()

    def _multicast_worker(self):
        MCAST_GRP = '224.0.0.251'
        MCAST_PORT = 5353

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        try:
            sock.bind(('', MCAST_PORT))
            mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
        except Exception as e:
            logger.debug(f"mDNS native bind exception: {e}")
            return

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                ip_str = addr[0]
                port = addr[1]

                # Basic DNS payload parse for readable strings
                raw_str = data.decode('latin1', errors='ignore')
                for srv_type, (friendly_name, cat, vendor) in KNOWN_MDNS_SERVICES.items():
                    clean_type = srv_type.replace(".local.", "")
                    if clean_type in raw_str or srv_type in raw_str:
                        dev_id = f"mdns:{ip_str}:{port}"
                        angle, _, dist = calculate_radar_coordinates(dev_id, protocol_hint="mDNS")
                        device = Device(
                            id=dev_id,
                            name=f"{friendly_name} ({ip_str})",
                            protocol=SignalProtocol.MDNS,
                            vendor=vendor,
                            category=cat,
                            rssi=-50,
                            estimated_distance_m=dist,
                            radar_angle=angle,
                            ip_address=ip_str,
                            port=port,
                            service_type=srv_type,
                            metadata={"raw_length": len(data)},
                            first_seen=datetime.now(),
                            last_seen=datetime.now()
                        )
                        self.on_device_discovered(device)
                        break
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"mDNS error: {e}")
                time.sleep(0.5)

        try:
            sock.close()
        except Exception:
            pass

    def stop(self):
        """Stops the scanner cleanly."""
        self._running = False
        if self._zeroconf:
            try:
                self._zeroconf.close()
            except Exception:
                pass
