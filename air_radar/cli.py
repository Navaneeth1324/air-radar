"""
AirRadar Command-Line Interface
"""
import argparse
import sys
import os
import json
import signal
import time

from air_radar.core.engine import RadarEngine
from air_radar.web.app import run_web_server
from air_radar.tui.tui_app import run_tui


BANNER = r"""
   _____  .__      __________             .___            
  /  _  \ |__|____ \______   \_____     __| _/____ _______
 /  /_\  \|  \__  \ |       _/\__  \   / __ |\__  \\_  __ \
/    |    \  |/ __ \|    |   \ / __ \_/ /_/ | / __ \|  | \/
\____|__  /__|____  /____|_  /(____  /\____ |(____  /__|   
        \/        \/       \/      \/      \/     \/       
  >> Passive Wireless, BLE & IoT Broadcast Environment Radar <<
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="air-radar",
        description="AirRadar: Passive Wireless, BLE, mDNS & SSDP Physical Radar Dashboard"
    )
    parser.add_argument("--web", action="store_true", help="Launch Sci-Fi Web Radar UI at localhost:8888")
    parser.add_argument("--tui", action="store_true", help="Run interactive Terminal TUI live monitor")
    parser.add_argument("--demo", action="store_true", help="Run in simulation mode with synthetic wireless signals")
    parser.add_argument("--port", type=int, default=8888, help="Web dashboard port (default: 8888)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Web dashboard host (default: 127.0.0.1)")
    parser.add_argument("--no-ble", action="store_true", help="Disable Bluetooth Low Energy scanning")
    parser.add_argument("--no-mdns", action="store_true", help="Disable mDNS / Bonjour ZeroConf scanning")
    parser.add_argument("--no-ssdp", action="store_true", help="Disable SSDP / UPnP scanning")
    parser.add_argument("--export", type=str, help="Save discovered device telemetry to a JSON file on exit")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    print(BANNER)

    engine = RadarEngine(
        enable_ble=not args.no_ble,
        enable_mdns=not args.no_mdns,
        enable_ssdp=not args.no_ssdp,
        demo_mode=args.demo
    )

    print("[*] Initializing signal discovery engines...")
    if args.demo:
        print("[!] Running in DEMO / SIMULATION mode (synthetic wireless airwaves).")
    else:
        if not args.no_ble:
            print("  [+] BLE Proximity & Tracker Engine: ACTIVE")
        if not args.no_mdns:
            print("  [+] mDNS / Bonjour ZeroConf Engine: ACTIVE")
        if not args.no_ssdp:
            print("  [+] SSDP / UPnP Broadcast Engine: ACTIVE")

    engine.start()

    def handle_exit(signum, frame):
        print("\n[*] Stopping discovery engines...")
        engine.stop()
        if args.export:
            try:
                devices = [d.to_dict() for d in engine.get_all_devices()]
                posture = engine.get_posture()
                with open(args.export, "w", encoding="utf-8") as f:
                    json.dump({"devices": devices, "posture": posture}, f, indent=2)
                print(f"[✓] Telemetry saved to {args.export}")
            except Exception as e:
                print(f"[!] Failed to export JSON: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if args.web:
        run_web_server(engine, host=args.host, port=args.port)
    elif args.tui:
        run_tui(engine)
    else:
        # Default mode: Launch web UI if no flag passed
        print("\n[i] No UI mode specified. Defaulting to Web UI.")
        print("    Tip: Use `air-radar --tui` for terminal mode or `air-radar --help` for options.\n")
        run_web_server(engine, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
