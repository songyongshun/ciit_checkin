import argparse
from . import server, admin  # ✅ 导入 admin 模块
from typing import Optional
import os
import yaml
import qrcode
from PIL import ImageDraw, ImageFont

def checkin_server(host: str = "127.0.0.1", port: int = 8000, config: Optional[str] = None):
    """Start the checkin HTTP server (blocking)."""
    # ✅ 解析命令行参数（当通过 'checkin' 命令调用时）
    parser = argparse.ArgumentParser(description="Start the CIIT check-in server.")
    parser.add_argument("-c", "--config", type=str, help="Path to room_info.yaml (default: src/checkin/room_info.yaml)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")

    # 解析命令行参数（如果被作为脚本调用）
    args = parser.parse_args()

    # 覆盖默认参数
    host = args.host
    port = args.port
    config = args.config or config  # 允许传入 config 参数覆盖

    # ✅ 获取默认教室编号用于提示
    room_number, _, _ = admin.load_classroom_config(config)
    if room_number is None:
        room_number = "1058"  # fallback

    print(f"Starting checkin server on {host}:{port} with config: {config}")
    print(f"Access the checkin page at http://{host}:{port}/checkin/{room_number}/checkin-01.html")

    return server.run_server(host=host, port=port, room_info_path=config)

def gen_qrcode(config: Optional[str] = None):
    """Generate QR codes for all seats based on room config."""
    parser = argparse.ArgumentParser(description="Generate QR codes for check-in pages.")
    parser.add_argument("-c", "--config", type=str, help="Path to room_info.yaml")
    args = parser.parse_args()
    config = args.config or config

    # Load config file to get public_ip and classroom layout
    config_path = config or os.path.join(os.path.dirname(__file__), 'room_info.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        public_ip = data.get('public_ip', 'localhost')
        classrooms = data.get('classrooms', [])
        if not classrooms:
            raise ValueError("No classrooms defined in config")
        room = classrooms[0]
        room_number = room.get('room_number', room.get('id', '1058'))
        row = room.get('row', 4)
        col = room.get('column', 12)
    except Exception as e:
        print(f"Failed to load config: {e}")
        public_ip = "localhost"
        room_number = "1058"
        row, col = 4, 12

    total_seats = min(row * col, 48)  # Cap at 48 as requested

    base_url = f"http://{public_ip}/checkin/{room_number}/checkin-{{:02d}}.html"

    # ✅ 创建 data/qrcode/{room_number} 目录
    output_dir = os.path.join("data", "qrcode", str(room_number))
    os.makedirs(output_dir, exist_ok=True)

    for num in range(1, total_seats + 1):
        url = base_url.format(num)
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()

        text = f"{num:02d}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        img_width, _ = img.size
        position = ((img_width - text_width) // 2, 5)
        draw.text(position, text, font=font, fill="black")

        filename = os.path.join(output_dir, f"qr-{num:02d}.png")
        img.save(filename)
        print(f"Saved: {filename}")