"""
AirRadar Security & Privacy Posture Engine
Analyzes physical signals and service broadcasts for privacy leaks and security risks.
"""
from typing import List, Dict, Any, Tuple
from air_radar.models.device import Device, RiskLevel, ThreatIndicator, SignalProtocol, DeviceCategory


# Insecure cleartext protocols commonly found on local networks
CLEARTEXT_SERVICE_PATTERNS = {
    "_http._tcp.local.": "Unencrypted HTTP web server exposed on local network.",
    "_ftp._tcp.local.": "Cleartext FTP service broadcasting on LAN.",
    "_telnet._tcp.local.": "Insecure Telnet daemon detected.",
    "_printer._tcp.local.": "Unauthenticated network printer queue open to LAN.",
}

# Tracking and surveillance hardware signatures
SUSPICIOUS_BLE_MANUFACTURERS = ["Apple, Inc.", "Tile, Inc."]


def audit_device(device: Device) -> List[ThreatIndicator]:
    """
    Performs security and privacy inspection on an individual device.
    """
    threats: List[ThreatIndicator] = []

    # Check 1: Insecure cleartext services
    if device.service_type:
        for pattern, desc in CLEARTEXT_SERVICE_PATTERNS.items():
            if pattern in device.service_type:
                threats.append(ThreatIndicator(
                    level=RiskLevel.WARN,
                    title="Cleartext Network Service",
                    description=desc,
                    remediation="Upgrade service to TLS/HTTPS or restrict binding to localhost."
                ))

    # Check 2: Apple AirTag / FindMy / Tile Beacons (Unsolicited Proximity Tracking)
    if device.protocol == SignalProtocol.BLE:
        if device.category == DeviceCategory.TRACKER or "FindMy" in device.name or "AirTag" in device.name:
            if device.rssi and device.rssi > -65:
                threats.append(ThreatIndicator(
                    level=RiskLevel.ALERT,
                    title="Active Tracker Nearby",
                    description=f"Strong signal ({device.rssi} dBm) from tracking beacon '{device.name}'. Could be following your location.",
                    remediation="Inspect physical belongings for unknown AirTags/Tiles."
                ))
            else:
                threats.append(ThreatIndicator(
                    level=RiskLevel.INFO,
                    title="BLE Beacon / Tracker Detected",
                    description=f"Passive tracker '{device.name}' in broadcast radius.",
                    remediation="Monitor if this tracker remains present across different locations."
                ))

    # Check 3: Cleartext port exposure
    if device.port in [80, 8080, 8000, 23, 21]:
        threats.append(ThreatIndicator(
            level=RiskLevel.WARN,
            title=f"Insecure Open Port ({device.port})",
            description=f"Device {device.name} is broadcasting an unencrypted port ({device.port}).",
            remediation="Ensure firewall prevents external exposure or use HTTPS/SSH."
        ))

    # Check 4: Suspicious unnamed BLE device broadcasting high power
    if device.protocol == SignalProtocol.BLE and (device.name == "Unknown Device" or not device.name):
        if device.rssi and device.rssi > -50:
            threats.append(ThreatIndicator(
                level=RiskLevel.WARN,
                title="Anonymous High-Power BLE Transmitter",
                description="Unidentified transmitter broadcasting at point-blank range without a device name.",
                remediation="Check nearby BLE peripherals or paired equipment."
            ))

    return threats


def calculate_environment_posture(devices: List[Device]) -> Dict[str, Any]:
    """
    Computes global security & privacy metrics across all discovered airwave signals.
    """
    total = len(devices)
    if total == 0:
        return {
            "score": 100,
            "status": "SECURE",
            "alert_count": 0,
            "warn_count": 0,
            "info_count": 0,
            "tracker_count": 0,
            "total_devices": 0
        }

    alert_count = 0
    warn_count = 0
    info_count = 0
    tracker_count = 0

    for d in devices:
        if d.category == DeviceCategory.TRACKER or "AirTag" in d.name or "Tile" in d.name:
            tracker_count += 1
        for t in d.threats:
            if t.level == RiskLevel.ALERT:
                alert_count += 1
            elif t.level == RiskLevel.WARN:
                warn_count += 1
            elif t.level == RiskLevel.INFO:
                info_count += 1

    # Calculate 0-100 privacy/security score
    deductions = (alert_count * 25) + (warn_count * 10) + (info_count * 2)
    score = max(0, min(100, 100 - deductions))

    if score >= 85:
        status = "EXCELLENT"
    elif score >= 65:
        status = "MODERATE"
    elif score >= 40:
        status = "EXPOSED"
    else:
        status = "HIGH_RISK"

    return {
        "score": score,
        "status": status,
        "alert_count": alert_count,
        "warn_count": warn_count,
        "info_count": info_count,
        "tracker_count": tracker_count,
        "total_devices": total
    }
