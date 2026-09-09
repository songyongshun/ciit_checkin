from http.server import ThreadingHTTPServer
from typing import Optional
from .checkinhandler import CheckinHandler
from .database import init_database, add_classroom

def run_server(host: str = "127.0.0.1", port: int = 8000, room_info_path: Optional[str] = None):
    # 初始化数据库
    init_database()
    # public_ip 用于二维码生成和管理页展示，优先取配置文件里的值
    public_ip = host  # 未配置时回退到监听地址 host
    # 若指定了房间配置文件，则加载教室配置到数据库
    if room_info_path:
        try:
            import yaml
            with open(room_info_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for room in data.get("classrooms", []):
                add_classroom(str(room["id"]), int(room.get("row")), int(room.get("column")))
            # 若配置里显式指定了 public_ip，则用它（可填公网 IP 或域名）
            configured_ip = data.get("public_ip")
            if configured_ip:
                public_ip = str(configured_ip).strip()
        except Exception as e:
            print(f"Failed to load room info config {room_info_path}: {e}")
    
    # 设置 public_ip 与 public_port（供二维码生成 / 管理页展示使用）
    CheckinHandler.public_ip = public_ip
    CheckinHandler.public_port = int(port)
    
    addr = (host, int(port))
    server = ThreadingHTTPServer(addr, CheckinHandler)
    print(f"Serving on http://{addr[0]}:{addr[1]}/checkin/ (ThreadingHTTPServer - concurrent requests supported)")
    print(f"Manage config at http://{addr[0]}:{addr[1]}/checkin/manage.html")
    print(f"Public IP (used in QR codes): {public_ip}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.server_close()
    return server


if __name__ == "__main__":
    run_server()