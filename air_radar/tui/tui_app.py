"""
AirRadar Terminal TUI Dashboard
Renders real-time live terminal monitoring table and security alerts.
Supports rich terminal layouts with automatic ANSI fallback.
"""
import time
import os
import sys
from datetime import datetime
from air_radar.core.engine import RadarEngine
from air_radar.models.device import RiskLevel


def run_tui(engine: RadarEngine):
    """Starts the interactive Terminal UI."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.live import Live
        from rich.panel import Panel
        from rich.layout import Layout
        from rich.text import Text
        _run_rich_tui(engine)
    except ImportError:
        _run_ansi_tui(engine)


def _run_rich_tui(engine: RadarEngine):
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text

    console = Console()

    def generate_table() -> Table:
        table = Table(title="📡 LIVE WIRELESS & IOT BROADCAST REGISTRY", expand=True, border_style="cyan")
        table.add_column("Protocol", style="magenta", width=8)
        table.add_column("Device Name", style="bold white", width=26)
        table.add_column("Vendor", style="cyan", width=18)
        table.add_column("Category", style="yellow", width=12)
        table.add_column("RSSI", justify="right", style="green", width=10)
        table.add_column("Est. Dist", justify="right", style="blue", width=10)
        table.add_column("Security Posture", style="red", width=22)

        devices = engine.get_all_devices()
        # Sort by active RSSI (closest first)
        sorted_devs = sorted(devices, key=lambda d: (d.rssi or -120), reverse=True)

        for dev in sorted_devs[:20]:  # Top 20
            rssi_str = f"{dev.rssi} dBm" if dev.rssi else "-"
            dist_str = f"~{dev.estimated_distance_m:.1f}m" if dev.estimated_distance_m else "-"
            
            # Format threat
            if dev.threats:
                top_threat = dev.threats[0]
                if top_threat.level == RiskLevel.ALERT:
                    threat_str = f"[bold red]⚠️ {top_threat.title}[/bold red]"
                else:
                    threat_str = f"[yellow]⚡ {top_threat.title}[/yellow]"
            else:
                threat_str = "[green]✓ Safe[/green]"

            table.add_row(
                dev.protocol.value,
                dev.name[:25],
                dev.vendor[:17],
                dev.category.value,
                rssi_str,
                dist_str,
                threat_str
            )
        return table

    def generate_header() -> Panel:
        posture = engine.get_posture()
        score_color = "green" if posture["score"] > 75 else "yellow" if posture["score"] > 50 else "red"
        text = Text()
        text.append(" AIR_RADAR ", style="bold black on cyan")
        text.append("  |  Active Signals: ", style="bold")
        text.append(f"{posture['total_devices']}", style="cyan bold")
        text.append("  |  Trackers/Beacons: ", style="bold")
        text.append(f"{posture['tracker_count']}", style="magenta bold")
        text.append("  |  Threats: ", style="bold")
        text.append(f"{posture['alert_count'] + posture['warn_count']}", style="red bold")
        text.append("  |  Privacy Score: ", style="bold")
        text.append(f"{posture['score']}/100 [{posture['status']}]", style=f"bold {score_color}")
        return Panel(text, border_style="cyan")

    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body")
    )

    with Live(layout, refresh_per_second=3, console=console):
        try:
            while True:
                layout["header"].update(generate_header())
                layout["body"].update(generate_table())
                time.sleep(0.33)
        except KeyboardInterrupt:
            pass


def _run_ansi_tui(engine: RadarEngine):
    """ANSI escape sequences fallback when Rich is not installed."""
    spinners = ["/", "-", "\\", "|"]
    idx = 0
    try:
        while True:
            posture = engine.get_posture()
            devices = engine.get_all_devices()
            os.system('clear' if os.name != 'nt' else 'cls')

            spinner = spinners[idx % len(spinners)]
            idx += 1

            print("=" * 80)
            print(f" 📡 AIR_RADAR [{spinner}]  |  Total: {posture['total_devices']}  |  Trackers: {posture['tracker_count']}  |  Score: {posture['score']}/100 ({posture['status']})")
            print("=" * 80)
            print(f"{'PROTOCOL':<8} {'DEVICE NAME':<26} {'VENDOR':<18} {'RSSI':<10} {'DIST':<8} {'STATUS'}")
            print("-" * 80)

            for d in devices[:15]:
                rssi = f"{d.rssi} dBm" if d.rssi else "LAN"
                dist = f"~{d.estimated_distance_m:.1f}m" if d.estimated_distance_m else "-"
                status = "⚠️ ALERT" if d.threats and d.threats[0].level == RiskLevel.ALERT else "SAFE"
                print(f"{d.protocol.value:<8} {d.name[:25]:<26} {d.vendor[:17]:<18} {rssi:<10} {dist:<8} {status}")

            print("=" * 80)
            print("Press Ctrl+C to exit.")
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
