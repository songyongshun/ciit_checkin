import importlib.resources
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import urllib.parse
import subprocess
from . import admin
import qrcode
from PIL import ImageDraw, ImageFont
import sqlite3

DATABASE_PATH = "checkin.db"

def init_database():
    """初始化数据库，创建 classrooms 和 students 表"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classrooms (
            id TEXT PRIMARY KEY,
            row INTEGER NOT NULL,
            column INTEGER NOT NULL
        )
    ''')
    # 创建 students 表，student_id 唯一
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL
        )
    ''')
    # 插入默认教室（仅当表为空时）
    cursor.execute("SELECT COUNT(*) FROM classrooms")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO classrooms (id, row, column) VALUES (?, ?, ?)", ("0001", 4, 12))
    conn.commit()
    conn.close()

def get_all_classrooms():
    """从数据库获取所有教室配置"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, row, column FROM classrooms")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "row": r[1], "column": r[2]} for r in rows]

def add_classroom(classroom_id, row, column):
    """添加教室到数据库"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO classrooms (id, row, column) VALUES (?, ?, ?)",
                   (classroom_id, row, column))
    conn.commit()
    conn.close()

def delete_classroom(classroom_id):
    """从数据库删除教室"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM classrooms WHERE id = ?", (classroom_id,))
    conn.commit()
    conn.close()

def get_classroom_by_id(classroom_id):
    """根据 ID 获取教室配置"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, row, column FROM classrooms WHERE id = ?", (classroom_id,))
    row = cursor.fetchone()
    conn.close()
    return row  # (id, row, col) or None

def get_class_student_counts():
    """获取每个班级的学生数量"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT class_name, COUNT(*) as count 
        FROM students 
        GROUP BY class_name 
        ORDER BY class_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"class_name": r[0], "count": r[1]} for r in rows]

def delete_students_by_class(class_name):
    """删除指定班级的所有学生"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE class_name = ?", (class_name,))
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

class CheckinHandler(BaseHTTPRequestHandler):
    public_ip = "127.0.0.1"  # 将作为实例属性或通过 run_server 设置

    def _render_form(self, message=''):
        try:
            html_content = importlib.resources.read_text('checkin', 'checkin.html', encoding='utf-8')
        except FileNotFoundError:
            html_content = "<html><body><h2>页面丢失</h2></body></html>"
        except Exception:
            html_content = "<html><body><h2>模板加载失败</h2></body></html>"

        msg_html = f'<p style="color:green">{message}</p>' if message else ''
        html_content = html_content.replace('{{message}}', msg_html)
        return html_content.encode('utf-8')

    def _render_admin(self, table_html='', classroom_id=''):  # ✅ 参数名改为 classroom_id
        try:
            tpl_content = importlib.resources.read_text('checkin', 'admin.html', encoding='utf-8')
        except FileNotFoundError:
            tpl_content = "<html><body><h2>admin 模板丢失</h2></body></html>"
        except Exception:
            tpl_content = "<html><body><h2>模板加载失败</h2></body></html>"

        rendered = tpl_content.replace('{{table_html}}', table_html).replace('{{classroom_id}}', classroom_id)  # ✅ 使用 classroom_id
        return rendered.encode('utf-8')

    def _render_manage(self):
        try:
            return importlib.resources.read_text('checkin', 'manage.html', encoding='utf-8').encode('utf-8')
        except Exception:
            return b"<h2>Manage template missing</h2>"

    def _get_room_config(self, classroom_id):
        """从数据库获取教室信息"""
        print(f"[DEBUG] Looking for classroom_id: {classroom_id}")
        result = get_classroom_by_id(classroom_id)
        if result:
            print(f"[DEBUG] Found room config: {result}")
            return result
        print(f"[DEBUG] Classroom {classroom_id} not found")
        return (None, None, None)

    def _generate_qr_codes(self, classroom_id):
        """生成指定教室的二维码"""
        classroom_id, row, col = self._get_room_config(classroom_id)
        if not classroom_id:
            return False
            
        public_ip = CheckinHandler.public_ip
        total_seats = min(row * col, 48)
        
        # 创建输出目录
        output_dir = os.path.join("data", classroom_id, "qrcode")
        os.makedirs(output_dir, exist_ok=True)
        
        base_url = f"http://{public_ip}/checkin/{classroom_id}/checkin-{{:02d}}.html"
        
        for num in range(1, total_seats + 1):
            url = base_url.format(num)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            
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
            
        return True

    def _generate_latex_file(self, classroom_id):
        """生成 LaTeX 文件用于打印二维码"""
        classroom_id, row, col = self._get_room_config(classroom_id)
        if not classroom_id:
            return None
            
        total_seats = min(row * col, 48)
        output_dir = os.path.join("data", classroom_id, "qrcode")
        
        # 检查二维码文件是否存在
        for i in range(1, total_seats + 1):
            qr_file = os.path.join(output_dir, f"qr-{i:02d}.png")
            if not os.path.exists(qr_file):
                return None
        
        # 生成 LaTeX 内容
        latex_content = r"""\documentclass[a4paper,10pt]{article}
\usepackage[margin=1cm]{geometry}
\usepackage{graphicx}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{tikz}

\setlength{\parindent}{0pt}
\pagestyle{empty} 

\begin{document}

"""
        
        # 添加二维码包含命令
        for i in range(1, total_seats + 1):
            latex_content += f"  \\includegraphics[width=0.23\\textwidth]{{qr-{i:02d}.png}}%\n"
            if i < total_seats:
                remainder = (i - 1) % 4
                if remainder == 3:
                    latex_content += "  \\par\n"
                else:
                    latex_content += "  \\hfill\n"
        
        latex_content += r"\end{document}"
        
        # 保存 LaTeX 文件
        tex_file = os.path.join(output_dir, f"qrcode-{classroom_id}.tex")
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)
            
        return tex_file

    def _compile_latex_to_pdf(self, tex_file_path):
        """调用 pdflatex 编译 LaTeX 文件为 PDF"""
        try:
            # 获取 LaTeX 文件所在目录
            tex_dir = os.path.dirname(tex_file_path)
            tex_filename = os.path.basename(tex_file_path)
            
            # 在 LaTeX 文件目录中执行 pdflatex
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', tex_filename],
                cwd=tex_dir,
                capture_output=True,
                text=True,
                timeout=30  # 30秒超时
            )
            
            if result.returncode == 0:
                pdf_file = tex_file_path.replace('.tex', '.pdf')
                if os.path.exists(pdf_file):
                    return pdf_file
            else:
                print(f"pdflatex error: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("pdflatex timeout")
            return None
        except FileNotFoundError:
            print("pdflatex not found. Please install LaTeX distribution.")
            return None
        except Exception as e:
            print(f"Error compiling LaTeX: {e}")
            return None

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        # 新增：提供 qrcode 目录下的静态文件（PDF/PNG）
        qr_match = re.match(r'^/checkin/(\d{3,4})/qrcode/(.+)$', path)
        if qr_match:
            classroom_id = qr_match.group(1)
            filename = qr_match.group(2)
            
            # 安全校验：只允许 .pdf 和 .png
            if not (filename.endswith('.pdf') or filename.endswith('.png')):
                self.send_response(403)
                self.end_headers()
                return

            file_path = os.path.join("data", classroom_id, "qrcode", filename)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                if filename.endswith('.pdf'):
                    self.send_header('Content-Type', 'application/pdf')
                else:
                    self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Disposition', f'inline; filename="{filename}"')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"<h2>File not found</h2>")
            return

        # ✅ 修改路由: /checkin/manage.html
        if path == "/checkin/manage.html":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self._render_manage())
            return

        # 新增：列出所有教室
        if path == "/checkin/manage/list":
            classrooms = get_all_classrooms()
            public_ip = getattr(CheckinHandler, 'public_ip', 'localhost')
            
            html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>教室列表</title></head><body>"
            html += "<h2>当前配置的教室</h2>"
            html += f"<p><strong>公共IP:</strong> {public_ip}</p>"
            html += "<ul>"
            for room in classrooms:
                html += f"<li>教室ID: {room['id']}, 行: {room['row']}, 列: {room['column']} "
                html += f'<a href="/checkin/{room["id"]}/admin.html" style="margin-left:10px;">查看教室签到情况</a></li>'
            html += "</ul>"
            html += '<p><a href="/checkin/manage.html">返回管理页面</a></p>'
            html += "</body></html>"
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        # ✅ 匹配 /checkin/{id}/admin.html 或 /checkin/{id}/checkin-XX.html
        match = re.match(r'^/checkin/(\d{3,4})/(admin\.html|checkin-\d{2}\.html)$', path)
        if match:
            classroom_id = match.group(1)
            page_type = match.group(2)

            # 使用内存配置替代文件加载
            classroom_id, _, _ = self._get_room_config(classroom_id)  # ✅ 接收 id
            if classroom_id is None:
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h2>教室配置未找到</h2>".encode('utf-8'))
                return

            if page_type == "admin.html":
                # 构建表格时也使用内存配置
                table_html = self._build_table_html(classroom_id)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self._render_admin(table_html=table_html, classroom_id=classroom_id))  # ✅ 传递 classroom_id
                return

            elif page_type.startswith("checkin-"):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self._render_form())
                return

        # 新增：列出已导入的班级及学生数量
        if path == "/checkin/manage/list-students":
            classes = get_class_student_counts()
            
            html = '<div style="font-family: Arial, sans-serif;">'
            if not classes:
                html += "<p>暂无导入的班级数据</p>"
            else:
                for cls in classes:
                    html += f'''
                    <div class="class-item">
                        <span><strong>{cls["class_name"]}</strong> ({cls["count"]} 名学生)</span>
                        <button class="delete-btn" onclick="parent.deleteClass('{cls["class_name"]}')">删除班级</button>
                    </div>
                    '''
            html += '</div>'
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        # 新增：返回导入学生页面（动态生成）
        if path == "/checkin/import-student.html":
            html = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>导入学生名单</title>
  <style>
    body { font-family: sans-serif; padding: 20px; }
    .form-group { margin: 15px 0; }
    input, button { padding: 8px; }
    button { background: #4CAF50; color: white; border: none; cursor: pointer; }
  </style>
</head>
<body>
  <h2>导入班级学生名单</h2>
  <form method="POST" action="/checkin/manage/import-students" enctype="multipart/form-data">
    <div class="form-group">
      <label for="csv_file">选择 CSV 文件：</label>
      <input type="file" id="csv_file" name="csv_file" accept=".csv" required>
    </div>
    <button type="submit">上传并导入</button>
  </form>
  <p><a href="/checkin/manage.html">返回管理页面</a></p>
</body>
</html>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("<h2>无效路径，请通过 /checkin/{教室ID}/admin.html 访问</h2>".encode('utf-8'))

    def _build_table_html(self, classroom_id):
        """基于内存配置构建表格"""
        classroom_id, row, col = self._get_room_config(classroom_id)  # ✅ 接收 id
        if not classroom_id:
            return "<h2>配置错误</h2>"
        
        row = row or 4
        col = col or 12
        
        # 读取签到数据
        data_dir = "data"
        name_file = os.path.join(data_dir, f"name-{classroom_id}.txt")
        entries = {}
        if os.path.exists(name_file):
            with open(name_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(",", 1)
                    if len(parts) == 2:
                        entries[parts[0]] = parts[1]

        # 构建表格
        table = [["" for _ in range(col)] for _ in range(row)]
        for prefix_str, name in entries.items():
            try:
                idx = int(prefix_str) - 1
                r = idx // col
                c = idx % col
                if 0 <= r < row and 0 <= c < col:
                    table[r][c] = name
            except (ValueError, IndexError):
                continue

        # 生成HTML (倒序显示行)
        table_html = "<table border='1' style='width:100%; border-collapse: collapse;'>\n"
        for tr in reversed(table):  # 倒序显示
            table_html += "  <tr>\n"
            for cell in tr:
                table_html += f"    <td>{cell}</td>\n"
            table_html += "  </tr>\n"
        table_html += "</table>"
        return table_html

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        # ✅ 添加教室: /checkin/manage/add
        if path == "/checkin/manage/add":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            classroom_id = params.get("classroom_id", [""])[0]
            row = int(params.get("row", ["4"])[0])
            column = int(params.get("column", ["12"])[0])
            
            add_classroom(classroom_id, row, column)
            
            self.send_response(302)
            self.send_header('Location', f"/checkin/{classroom_id}/admin.html")
            self.end_headers()
            return

        # ✅ 删除教室: /checkin/manage/delete
        if path == "/checkin/manage/delete":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            classroom_id_to_delete = params.get("classroom_id", [""])[0]
            delete_classroom(classroom_id_to_delete)
            
            self.send_response(302)
            self.send_header('Location', "/checkin/manage.html")
            self.end_headers()
            return
    
            # ✅ 生成二维码: /checkin/manage/generate-qrcode
        if path == "/checkin/manage/generate-qrcode":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            classroom_id = params.get("classroom_id", [""])[0]
            
            if self._generate_qr_codes(classroom_id):
                message = f"二维码已生成到 ./data/{classroom_id}/qrcode/ 目录"
                # 添加下载按钮
                download_button = f'<form method="POST" action="/checkin/manage/generate-print-file" style="margin-top: 15px;">' \
                                f'<input type="hidden" name="classroom_id" value="{classroom_id}">' \
                                f'<button type="submit" class="btn-qrcode">下载打印文件</button>' \
                                f'</form>'
            else:
                message = "教室ID不存在，无法生成二维码"
                download_button = ""
            
            # 返回结果页面
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>二维码生成结果</title>
<style>
.btn-qrcode {{ 
    padding: 10px 20px; 
    background: #9C27B0; 
    color: white; 
    border: none; 
    cursor: pointer; 
    margin-top: 10px;
}}
</style>
</head>
<body>
<h2>二维码生成结果</h2>
<p>{message}</p>
{download_button}
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        # 新增：生成打印文件（LaTeX + PDF）
        if path == "/checkin/manage/generate-print-file":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            classroom_id = params.get("classroom_id", [""])[0]
            
            # 生成 LaTeX 文件
            tex_file = self._generate_latex_file(classroom_id)
            if tex_file:
                # 编译为 PDF
                pdf_file = self._compile_latex_to_pdf(tex_file)
                if pdf_file:
                    # 重定向到下载页面
                    download_url = f"/checkin/{classroom_id}/qrcode/qrcode-{classroom_id}.pdf"
                    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>打印文件生成成功</title></head>
<body>
<h2>打印文件生成成功</h2>
<p>PDF文件已生成，点击下面链接下载:</p>
<p><a href="{download_url}" style="font-size: 18px; color: #2196F3;">下载 qrcode-{classroom_id}.pdf</a></p>
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
                else:
                    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PDF生成失败</title></head>
<body>
<h2>PDF生成失败</h2>
<p>LaTeX文件已生成，但编译PDF失败。请确保已安装LaTeX发行版（如MiKTeX或TeX Live）。</p>
<p>LaTeX文件位置: {tex_file}</p>
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
            else:
                html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>LaTeX生成失败</title></head>
<body>
<h2>LaTeX生成失败</h2>
<p>无法生成LaTeX文件。请确保已先生成二维码。</p>
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        # 新增：导入学生名单
        if path == "/checkin/manage/import-students":
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._send_import_result("无效的请求类型", success=False)
                return

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            # 提取 boundary
            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                self._send_import_result("无效的 multipart 格式", success=False)
                return
            boundary = boundary_match.group(1).strip('"').encode()

            parts = body.split(b'--' + boundary)
            csv_content = None
            filename = None
            for part in parts:
                if b'name="csv_file"' in part:
                    # 提取文件名
                    filename_match = re.search(rb'filename="([^"]+)"', part)
                    if filename_match:
                        filename = filename_match.group(1).decode('utf-8')
                    header_end = part.find(b'\r\n\r\n')
                    if header_end != -1:
                        csv_content = part[header_end+4:]
                        if csv_content.endswith(b'\r\n'):
                            csv_content = csv_content[:-2]
                        break

            if not filename or not csv_content:
                self._send_import_result("未选择文件", success=False)
                return

            try:
                import csv
                from io import StringIO
                decoded = csv_content.decode('utf-8-sig')
                reader = csv.reader(StringIO(decoded))
                students = []
                seen_ids = set()
                duplicates = []
                for row in reader:
                    if len(row) >= 3:
                        student_id, name, class_name = row[0].strip(), row[1].strip(), row[2].strip()
                        if not student_id or not name or not class_name:
                            continue
                        if student_id in seen_ids:
                            duplicates.append(student_id)
                        else:
                            seen_ids.add(student_id)
                            students.append((student_id, name, class_name))
                
                if duplicates:
                    self._send_import_result(f"导入失败：发现重复学号 {', '.join(duplicates)}", success=False)
                    return

                if not students:
                    self._send_import_result(f"文件 '{filename}' 为空或格式不正确", success=False)
                    return

                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                try:
                    cursor.executemany(
                        "INSERT INTO students (student_id, name, class_name) VALUES (?, ?, ?)",
                        students
                    )
                    conn.commit()
                    self._send_import_result(f"成功导入 '{filename}' 中的 {len(students)} 名学生")
                except sqlite3.IntegrityError as e:
                    if "UNIQUE constraint failed" in str(e):
                        conn.rollback()
                        # 查询哪些学号已存在
                        placeholders = ','.join('?' for _ in seen_ids)
                        cursor.execute(f"SELECT student_id FROM students WHERE student_id IN ({placeholders})", tuple(seen_ids))
                        existing_ids = [row[0] for row in cursor.fetchall()]
                        conn.close()
                        self._send_import_result(f"导入失败：以下学号已存在 {', '.join(existing_ids)}", success=False)
                    else:
                        raise
                finally:
                    conn.close()

            except Exception as e:
                self._send_import_result(f"导入失败: {str(e)}", success=False)
            return

        # ✅ 匹配 /checkin/{id}/save 和 /checkin/{id}/reset
        save_match = re.match(r'^/checkin/(\d{3,4})/save$', path)
        reset_match = re.match(r'^/checkin/(\d{3,4})/reset$', path)

        if save_match:
            classroom_id = save_match.group(1)
            csv_filename = admin.save_csv_to_dir(classroom_id=classroom_id, room_info_path=None)
            redirect_url = f"/checkin/{classroom_id}/admin.html"
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
            redirect_url = f"/checkin/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>重置成功</title>
<meta http-equiv="refresh" content="1;url={redirect_url}"></head>
<body><p>数据已重置，1秒后返回...</p></body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        # Handle check-in POST: /checkin/{id}/checkin-XX.html
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
            # ✅ 提取 classroom_id 和 seq from /checkin/{id}/checkin-XX.html
            class_match = re.match(r'^/checkin/(\d{3,4})/checkin-(\d{2})\.html$', path)
            if not class_match:
                self.send_response(400)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h2>签到请求路径无效，请通过 /checkin/{教室ID}/checkin-XX.html 提交</h2>".encode('utf-8'))
                return

            classroom_id = class_match.group(1)
            seq = class_match.group(2)

            data_dir = "data"
            os.makedirs(data_dir, exist_ok=True)
            name_file = os.path.join(data_dir, f"name-{classroom_id}.txt")

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


    def _send_import_result(self, message, success=True):
        """返回导入结果页面"""
        status = 200 if success else 400
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>导入结果</title></head>
<body>
<h2>导入结果</h2>
<p>{message}</p>
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))


def run_server(host: str = "127.0.0.1", port: int = 8000, room_info_path=None):
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