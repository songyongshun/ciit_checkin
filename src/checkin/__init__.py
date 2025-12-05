from . import server
from typing import Optional

def checkin_server(host: str = "127.0.0.1", port: int = 8000, config: Optional[str] = None):
    """Start the checkin HTTP server (blocking)."""
    return server.run_server(host=host, port=port, room_info_path=config)