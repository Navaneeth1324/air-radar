"""
AirRadar SSDP / UPnP Discovery Engine
Sends periodic M-SEARCH broadcast queries and listens on 239.255.255.250:1900
for smart TVs, media servers, routers, and IoT hubs.
"""
import socket
import threading
import time
import re
import logging
from typing import Callable, Optional, Dict
from datetime import datetime

from air_radar.models.device import Device, SignalProtocol, DeviceCategory
from air_radar.core.distance import calculate_radar_coordinates

logger = logging.getLogger(__name__)

SSDP_MSEARCH_MSG = (
    'M-SEARCH * HTTP/1.1\r\n'
    'HOST: 239.255.255.250:1900\r\n'
    'MAN: "ssdp:discover"\r\n'
    'MX: 2\r\n'
    'ST: ssdp:all\r\n'
    '\r\n'
).encode('utf-8')


class SSDPScanner:
    """
    Passively and actively discovers UPnP/SSDP devices using standard library UDP sockets.
    """
    def __init__(self, on_device_discovered: Callable[[Device], None]):
        self.on_device_discovered = on_device_discovered
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts SSDP discovery in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _parse_headers(self, response_text: str) -> Dict[str, str]:
        headers = {}
        for line in response_text.split('\r\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                headers[key.strip().upper()] = val.strip()
        return headers

    def _categorize_ssdp(self, server_str: str, st_str: str) -> Tuple[str, DeviceCategory, str]:
        combined = f"{server_str} {st_str}".lower()
        if "roku" in combined:
            return "Roku Streaming Device", DeviceCategory.TV_MEDIA, "Roku, Inc."
        elif "samsung" in combined or "tizen" in combined:
            return "Samsung Smart TV", DeviceCategory.TV_MEDIA, "Samsung Electronics"
        elif "lg" in combined or "webos" in combined:
            return "LG Smart TV", DeviceCategory.TV_MEDIA, "LG Electronics"
        elif "sonos" in combined:
            return "Sonos Player", DeviceCategory.AUDIO, "Sonos, Inc."
        elif "synology" in combined or "qnap" in combined or "nas" in combined:
            return "Network Attached Storage (NAS)", DeviceCategory.NETWORK, "NAS Vendor"
        elif "router" in combined or "gateway" in combined or "igd" in combined:
            return "Internet Gateway / Router", DeviceCategory.NETWORK, "Router"
        elif "philips" in combined or "hue" in combined:
            return "Philips Hue", DeviceCategory.SMART_HOME, "Philips"
        return "UPnP Device", DeviceCategory.NETWORK, "UPnP Device"

    def _worker(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(2.0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        last_search_time = 0.0

        while self._running:
            now = time.time()
            # Broadcast M-SEARCH query every 15 seconds
            if now - last_search_time > 15.0:
                try:
                    sock.sendto(SSDP_MSEARCH_MSG, ('239.255.255.250', 1900))
                    last_search_time = now
                except Exception as e:
                    logger.debug(f"SSDP broadcast error: {e}")

            try:
                data, addr = sock.recvfrom(4096)
                text = data.decode('utf-8', errors='ignore')
                headers = self._parse_headers(text)

                ip_str = addr[0]
                server = headers.get('SERVER', '')
                st = headers.get('ST', headers.get('NT', ''))
                location = headers.get('LOCATION', '')
                usn = headers.get('USN', '')

                friendly_name, cat, vendor = self._categorize_ssdp(server, st)
                dev_id = f"ssdp:{usn or ip_str}"
                angle, _, dist = calculate_radar_coordinates(dev_id, protocol_hint="SSDP")

                # Extract port from location URL if present
                port = None
                port_match = re.search(r':(\d+)/', location)
                if port_match:
                    port = int(port_match.group(1))

                device = Device(
                    id=dev_id,
                    name=f"{friendly_name} ({ip_str})",
                    protocol=SignalProtocol.SSDP,
                    vendor=vendor,
                    category=cat,
                    rssi=-60,
                    estimated_distance_m=dist,
                    radar_angle=angle,
                    ip_address=ip_str,
                    port=port,
                    service_type=st or "urn:schemas-upnp-org:device",
                    metadata={
                        "server": server,
                        "location": location,
                        "usn": usn
                    },
                    first_seen=datetime.now(),
                    last_seen=datetime.now()
                )
                self.on_device_discovered(device)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"SSDP receive loop error: {e}")
                time.sleep(0.5)

        try:
            sock.close()
        except Exception:
            pass

    def stop(self):
        """Stops the scanner."""
        self._running = False
