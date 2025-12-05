import argparse
from . import checkin_server

def main():
    parser = argparse.ArgumentParser(description="Start the CIIT check-in server.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--config", type=str, default=None, help="Path to room info config")
    args = parser.parse_args()

    checkin_server(host=args.host, port=args.port, config=args.config)

if __name__ == "__main__":
    main()