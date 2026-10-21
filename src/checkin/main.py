import argparse
import sys
from . import server


def main():
    parser = argparse.ArgumentParser(description="Start the CIIT check-in server.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("-r", "--room", type=str, default=None,
                        help="Path to room info config (e.g. room_info.yaml)")
    parser.add_argument("--public", type=str, default=None,
                        help="Public IPv4 address used in QR codes / manage page. "
                             "Accepts an IPv4 address only (no port, no domain, no IPv6); "
                             "the port comes from --port. "
                             "Required when --host is 0.0.0.0, otherwise defaults to --host.")
    args = parser.parse_args()

    try:
        server.run_server(host=args.host, port=args.port, room_info_path=args.room,
                           public_ip=args.public)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()