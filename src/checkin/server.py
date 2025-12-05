from http.server import HTTPServer
from .checkinhandler import CheckinHandler
from .database import init_database

def run_server(host: str = "127.0.0.1", port: int = 8000):
    # 初始化数据库
    init_database()
    
    # 设置 public_ip
    CheckinHandler.public_ip = host
    
    addr = (host, int(port))
    server = HTTPServer(addr, CheckinHandler)
    print(f"Serving on http://{addr[0]}:{addr[1]}/checkin/")
    print(f"Manage config at http://{addr[0]}:{addr[1]}/checkin/manage.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.server_close()
    return server


if __name__ == "__main__":
    run_server()