import ipaddress
from http.server import ThreadingHTTPServer
from typing import Optional
from .checkinhandler import CheckinHandler
from .database import init_database, add_classroom

# 通配监听地址：监听所有网卡，此时必须显式提供对外访问的 IP
WILDCARD_HOSTS = {"0.0.0.0"}


def is_wildcard_host(host: str) -> bool:
    """判断 host 是否为通配监听地址（0.0.0.0）。"""
    return (host or "").strip() in WILDCARD_HOSTS


def validate_public_ip(value: Optional[str]) -> str:
    """
    校验 --public 参数：只接受 IPv4 地址。
    - 不接受带端口的形式（如 "1.2.3.4:8080"），端口由 --port 单独提供；
    - 不接受域名，不支持 IPv6。
    返回规范化后的 IP 字符串；值为空则返回空串；非法则抛出 ValueError。
    """
    text = (value or "").strip()
    if not text:
        return ""

    if ":" in text:
        if text.count(":") == 1:
            # "1.2.3.4:8080" 形式：显式拒绝并提示改用 --port
            head, tail = text.rsplit(":", 1)
            if head and tail.isdigit():
                raise ValueError(
                    f"--public 不接受端口: {value!r}；请只填写 IP 地址，端口由 --port 指定")
        # 含多个冒号：IPv6 或其它非法写法
        raise ValueError(f"--public 只支持 IPv4 地址，不支持 IPv6: {value!r}")

    try:
        ip = ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(
            f"--public 只接受 IPv4 IP 地址（不支持域名），无效值: {value!r}")
    return str(ip)


def run_server(host: str = "127.0.0.1", port: int = 8000, room_info_path: Optional[str] = None,
               public_ip: Optional[str] = None):
    # public_ip 用于二维码生成和管理页展示，只由命令行 --public 提供（仅接受 IP 地址）
    public_ip = validate_public_ip(public_ip)
    # 监听通配地址时，扫码地址无法推导，必须显式提供对外 IP
    if is_wildcard_host(host) and not public_ip:
        raise ValueError(
            f"--host 为 {host}（监听所有网卡）时，必须通过 --public 指定对外访问的 IP 地址，"
            f"例如：--public 47.103.9.15")
    # 初始化数据库
    init_database()
    # 若指定了房间配置文件，则加载教室配置到数据库
    if room_info_path:
        try:
            import yaml
            with open(room_info_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if data.get("public_ip"):
                print("提示: 配置文件中的 public_ip 已不再生效，请改用命令行参数 --public 指定")
            for room in data.get("classrooms", []):
                add_classroom(str(room["id"]), int(room.get("row")), int(room.get("column")))
        except Exception as e:
            print(f"Failed to load room info config {room_info_path}: {e}")

    # 兜底：未指定 --public 时回退到监听地址（非通配地址时）
    public_ip = public_ip or (host or "").strip()

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