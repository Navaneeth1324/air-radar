"""
AirRadar Web Server
Serves the Sci-Fi Radar visualizer and broadcasts real-time device updates via WebSockets.
"""
import os
import json
import asyncio
import logging
from typing import List
from pathlib import Path

from air_radar.core.engine import RadarEngine
from air_radar.models.device import Device

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_fastapi_app(engine: RadarEngine):
    """Creates a FastAPI instance with WebSocket streaming."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="AirRadar", description="Wireless & IoT Environment Radar")

    # In-memory connected websocket clients
    active_websockets: List[WebSocket] = []
    loop: asyncio.AbstractEventLoop = None

    @app.on_event("startup")
    async def startup_event():
        nonlocal loop
        loop = asyncio.get_running_loop()

        # Wire engine listener to broadcast through async event loop
        def on_device_event(device: Device):
            if not loop or loop.is_closed():
                return
            msg = json.dumps({
                "type": "DEVICE_UPDATE",
                "device": device.to_dict(),
                "posture": engine.get_posture()
            })
            asyncio.run_coroutine_threadsafe(_broadcast_message(msg), loop)

        engine.register_listener(on_device_event)

    async def _broadcast_message(msg: str):
        dead_clients = []
        for ws in active_websockets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead_clients.append(ws)
        for dead in dead_clients:
            if dead in active_websockets:
                active_websockets.remove(dead)

    @app.get("/")
    async def get_index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/devices")
    async def get_devices():
        devices = [d.to_dict() for d in engine.get_all_devices()]
        return JSONResponse({"devices": devices, "posture": engine.get_posture()})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        active_websockets.append(websocket)
        try:
            # Send initial state synchronization snapshot
            initial_data = json.dumps({
                "type": "SYNC_ALL",
                "devices": [d.to_dict() for d in engine.get_all_devices()],
                "posture": engine.get_posture()
            })
            await websocket.send_text(initial_data)

            while True:
                # Keep socket alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in active_websockets:
                active_websockets.remove(websocket)
        except Exception:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    # Mount static assets
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def run_web_server(engine: RadarEngine, host: str = "127.0.0.1", port: int = 8888):
    """
    Launches the web server. Uses uvicorn + fastapi if present,
    or falls back to a standard library HTTP server.
    """
    try:
        import uvicorn
        from fastapi import FastAPI
        app = create_fastapi_app(engine)
        print(f"\n[+] 🚀 AirRadar Web UI running at: http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except ImportError:
        # Standard library HTTP Server fallback
        print(f"\n[+] 🚀 Launching AirRadar native HTTP server at: http://{host}:{port}")
        _run_native_http_server(engine, host, port)


def _run_native_http_server(engine: RadarEngine, host: str, port: int):
    import http.server
    import socketserver

    class RadarHTTPHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

        def do_GET(self):
            if self.path == "/api/devices":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                data = json.dumps({
                    "type": "SYNC_ALL",
                    "devices": [d.to_dict() for d in engine.get_all_devices()],
                    "posture": engine.get_posture()
                })
                self.wfile.write(data.encode("utf-8"))
            elif self.path == "/" or self.path.startswith("/?"):
                self.path = "/index.html"
                return super().do_GET()
            else:
                return super().do_GET()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), RadarHTTPHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
