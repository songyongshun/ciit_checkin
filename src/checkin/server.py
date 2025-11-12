import importlib.resources
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import urllib.parse
from . import admin

class CheckinHandler(BaseHTTPRequestHandler):
    # Class-level variable to hold the config file path passed from run_server()
    room_info_path = None

    def _render_form(self, message=''):
        try:
            # ✅ 使用 importlib.resources 从包内读取文件
            html_content = importlib.resources.read_text('checkin', 'checkin.html', encoding='utf-8')
        except FileNotFoundError:
            html_content = "<html><body><h2>页面丢失</h2></body></html>"
        except Exception:
            html_content = "<html><body><h2>模板加载失败</h2></body></html>"

        msg_html = f'<p style="color:green">{message}</p>' if message else ''
        html_content = html_content.replace('{{message}}', msg_html)
        return html_content.encode('utf-8')

    def _render_admin(self, table_html='', room_number=''):
        try:
            # ✅ 同样方式读取 admin.html
            tpl_content = importlib.resources.read_text('checkin', 'admin.html', encoding='utf-8')
        except FileNotFoundError:
            tpl_content = "<html><body><h2>admin 模板丢失</h2></body></html>"
        except Exception:
            tpl_content = "<html><body><h2>模板加载失败</h2></body></html>"

        rendered = tpl_content.replace('{{table_html}}', table_html).replace('{{room_number}}', room_number)
        return rendered.encode('utf-8')

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        # Extract classroom ID from path: e.g., /1056/admin.html → id="1056"
        match = re.match(r'^/(\d{3,4})/(admin\.html|checkin-\d{2}\.html)$', path)
        if match:
            classroom_id = match.group(1)
            page_type = match.group(2)

            # Load config for this classroom
            room_number, _, _ = admin.load_classroom_config(self.room_info_path, classroom_id)
            if room_number is None:
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h2>教室配置未找到</h2>".encode('utf-8'))
                return

            if page_type == "admin.html":
                table_html = admin.build_table_html_from_namefile(classroom_id=classroom_id, room_info_path=self.room_info_path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self._render_admin(table_html=table_html, room_number=room_number or "未知教室"))
                return

            elif page_type.startswith("checkin-"):
                # For checkin pages, just show the form
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self._render_form())
                return

        # ❌ 删除：不再支持 /admin.html 默认页（必须通过 /{id}/admin.html 访问）
        # 所有访问必须带 classroom_id
        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("<h2>无效路径，请通过 /{教室ID}/admin.html 访问</h2>".encode('utf-8'))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        # ✅ 仅支持教室专属路径：/1056/save 和 /1056/reset
        save_match = re.match(r'^/(\d{3,4})/save$', path)
        reset_match = re.match(r'^/(\d{3,4})/reset$', path)

        if save_match:
            classroom_id = save_match.group(1)
            csv_filename = admin.save_csv_to_dir(classroom_id=classroom_id, room_info_path=self.room_info_path)
            redirect_url = f"/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>保存成功</title>
<meta http-equiv="refresh" content="2;url={redirect_url}"></head>
<body><p>签到记录已保存为 <code>{csv_filename}</code>，2秒后返回...</p></body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        if reset_match:
            classroom_id = reset_match.group(1)
            admin.reset_namefile(classroom_id=classroom_id)
            redirect_url = f"/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>重置成功</title>
<meta http-equiv="refresh" content="1;url={redirect_url}"></head>
<body><p>数据已重置，1秒后返回...</p></body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        # ❌ 删除：不再支持 /save 或 /reset 全局路径
        # ❌ 删除：不再支持从 Referer 推断教室 ID

        # Handle check-in POST (name submission) —— 仅允许 /{id}/checkin-XX.html
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        content_type = self.headers.get('Content-Type', '')

        name = None
        if 'application/json' in content_type:
            try:
                data = json.loads(body.decode('utf-8'))
                name = data.get('name') or data.get('user_id')
            except json.JSONDecodeError:
                name = None
        else:
            try:
                parsed = urllib.parse.parse_qs(body.decode('utf-8'))
                name = parsed.get('name', [None])[0]
            except Exception:
                name = None

        if name:
            # ✅ 1. 从路径提取 classroom_id（决定写入哪个文件）
            class_match = re.match(r'^/(\d{3,4})/checkin-\d{2}\.html$', path)
            classroom_id = class_match.group(1) if class_match else None

            # ✅ 2. 从路径提取签到序号（写入文件的第一列）
            seq_match = re.match(r'^.*/checkin-(\d{2})\.html$', path)
            seq = seq_match.group(1) if seq_match else '00'

            if not classroom_id:
                # ❌ 不再允许 fallback 到默认教室
                # 所有 checkin 请求必须来自 /{id}/checkin-XX.html
                self.send_response(400)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h2>签到请求路径无效，请通过 /{教室ID}/checkin-XX.html 提交</h2>".encode('utf-8'))
                return

            # ✅ 3. 构造文件名：data/name-1056.txt
            data_dir = "data"
            os.makedirs(data_dir, exist_ok=True)
            name_file = os.path.join(data_dir, f"name-{classroom_id}.txt")

            # ✅ 4. 写入：签到序号,姓名 → 如 "01,张三"
            with open(name_file, 'a', encoding='utf-8') as f:
                f.write(f"{seq},{name}\n")

            message = f"已保存: {name}"
            status = 200
        else:
            message = "Missing name or invalid data."
            status = 400

        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(self._render_form(message=message))


def run_server(host: str = "0.0.0.0", port: int = 8000, room_info_path=None):
    """Start the checkin HTTP server (blocking)."""
    # ✅ Set the room_info_path on the handler class
    CheckinHandler.room_info_path = room_info_path

    addr = (host, int(port))
    server = HTTPServer(addr, CheckinHandler)
    print(f"Serving on http://{addr[0]}:{addr[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.server_close()
    return server


if __name__ == "__main__":
    run_server()  # keep CLI behavior