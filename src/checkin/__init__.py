import argparse
from . import server
from typing import Optional

def checkin_server(host: str = "0.0.0.0", port: int = 8000, config: Optional[str] = None):
    """Start the checkin HTTP server (blocking)."""
    # ✅ 解析命令行参数（当通过 'checkin' 命令调用时）
    parser = argparse.ArgumentParser(description="Start the CIIT check-in server.")
    parser.add_argument("-c", "--config", type=str, help="Path to room_info.yaml (default: src/checkin/room_info.yaml)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    
    # 解析命令行参数（如果被作为脚本调用）
    args = parser.parse_args()

    # 覆盖默认参数
    host = args.host
    port = args.port
    config = args.config or config  # 允许传入 config 参数覆盖

    print(f"Starting checkin server on {host}:{port} with config: {config}")
    return server.run_server(host=host, port=port, room_info_path=config)