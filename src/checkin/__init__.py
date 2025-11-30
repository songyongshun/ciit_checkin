import argparse
from . import server
from typing import Optional

def checkin_server(host: str = "127.0.0.1", port: int = 8000, config: Optional[str] = None):
    """Start the checkin HTTP server (blocking)."""
    # ✅ 解析命令行参数
    parser = argparse.ArgumentParser(description="Start the CIIT check-in server.")
    parser.add_argument("--host", type=str, default=host, help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=port, help="Server port (default: 8000)")
    args = parser.parse_args()

    # 覆盖默认参数
    host = args.host
    port = args.port

    return server.run_server(host=host, port=port, room_info_path=config)