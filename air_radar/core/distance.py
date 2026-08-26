"""
AirRadar Distance & Coordinate Algorithms
Calculates distance from RSSI path-loss models and positions devices in polar space.
"""
import hashlib
import math
from typing import Optional, Tuple


# Default 1m reference RSSI for typical BLE beacons if TxPower is not broadcast
DEFAULT_MEASURED_POWER = -59.0
# Environmental path-loss exponent (2.0 = free space, 2.5-3.0 = indoor residential / office with walls)
DEFAULT_ENVIRONMENTAL_EXPONENT = 2.8


def calculate_distance_from_rssi(
    rssi: Optional[int],
    tx_power: Optional[int] = None,
    n: float = DEFAULT_ENVIRONMENTAL_EXPONENT
) -> Optional[float]:
    """
    Estimates distance in meters using Log-Distance Path Loss Model:
    d = 10 ^ ((MeasuredPower - RSSI) / (10 * n))
    """
    if rssi is None or rssi == 0:
        return None

    # Clamp RSSI to reasonable physical bounds (-110 dBm to -10 dBm)
    clamped_rssi = max(-110, min(-10, rssi))
    measured_power = float(tx_power) if tx_power is not None else DEFAULT_MEASURED_POWER

    ratio = (measured_power - clamped_rssi) / (10.0 * n)
    distance = math.pow(10.0, ratio)

    # Clamp distance to realistic room/building scale (0.2m to 50m)
    return max(0.2, min(50.0, distance))


def calculate_radar_coordinates(
    device_id: str,
    distance_m: Optional[float] = None,
    protocol_hint: str = "BLE"
) -> Tuple[float, float, float]:
    """
    Generates deterministic polar (angle, radius) and normalized Cartesian (x, y) coordinates
    so that devices don't randomly jump all over the radar screen on each packet.

    Returns:
        (angle_rad, normalized_radius, distance_m)
    """
    # Deterministic angle derived from SHA256 of device ID
    hash_int = int(hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:8], 16)
    angle = (hash_int % 360) * (math.pi / 180.0)

    # If no distance available (e.g. mDNS/SSDP network broadcast), use a default zone
    if distance_m is None:
        if protocol_hint == "mDNS":
            dist = 4.5
        elif protocol_hint == "SSDP":
            dist = 6.0
        else:
            dist = 8.0
    else:
        dist = distance_m

    # Normalize radius for 0.0 (center) to 1.0 (outer radar ring, ~25m)
    max_range = 25.0
    normalized_radius = min(1.0, max(0.08, dist / max_range))

    return angle, normalized_radius, dist
