import importlib.resources
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.parse
import subprocess
from .database import (
    get_all_classrooms,
    add_classroom,
    delete_classroom,
    get_classroom_by_id,
    get_class_student_counts,
    delete_students_by_class_name,
    DATABASE_PATH,
)
import qrcode
from PIL import ImageDraw, ImageFont
import sqlite3

class CheckinHandler(BaseHTTPRequestHandler):
    public_ip = "127.0.0.1"  # 将作为实例属性或通过 run_server 设置

    # 全局签到状态字典：classroom_id -> bool (True=允许签到)
    checkin_enabled = {}

    # 内联 admin 页面模板（不再使用外部文件）
    _admin_template = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>姓名记录管理</title>
  <style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
  }}
  .container {{
    max-width: 800px;
    margin: 0 auto;
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }}
  h2 {{
    text-align: center;
    color: #333;
    margin-bottom: 20px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
  }}
  td {{
    padding: 8px;
    text-align: center;
    border: 1px solid #ddd;
  }}
  .btn {{
    display: block;
    width: 200px;
    margin: 10px auto;
    padding: 10px;
    background-color: #4CAF50;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 16px;
    text-decoration: none;
    text-align: center;
  }}
  .btn:hover {{
    background-color: #45a049;
  }}
  .btn-reset {{
    background-color: #f44336;
  }}
  .btn-reset:hover {{
    background-color: #da190b;
  }}
  .btn-start {{
    background-color: #2196F3;
  }}
  .btn-start:hover {{
    background-color: #0b7dda;
  }}
  .btn-stop {{
    background-color: #ff9800;
  }}
  .btn-stop:hover {{
    background-color: #e68a00;
  }}
  .btn-record {{
    background-color: #9C27B0;
  }}
  .btn-record:hover {{
    background-color: #7B1FA2;
  }}
  .label {{
    text-align: center;
    margin-top: 15px;
    font-weight: bold;
    color: #666;
    font-size: 18px;
  }}
  .status {{
    text-align: center;
    margin: 10px 0;
    font-size: 18px;
    font-weight: bold;
    color: #e91e63;
  }}
  .record-table {{
    width: 100%;
    margin-top: 20px;
    border: 1px solid #ddd;
    border-collapse: collapse;
  }}
  .record-table th, .record-table td {{
    padding: 10px;
    text-align: left;
    border: 1px solid #ddd;
  }}
  .record-table th {{
    background-color: #f2f2f2;
  }}
  </style>
</head>
<body>
  <div class="container">
  <h2>签到情况</h2>
  {table_html}
  <div class="label">讲台</div>
  <div class="status">{status_text}</div>
  <form method="POST" action="/checkin/{classroom_id}/save">
    <div class="form-group">
      <label for="course">课程名称:</label>
      <input type="text" id="course" name="course" required>
    </div>
    <button type="submit" class="btn">保存</button>
    <button type="submit" class="btn btn-record" formaction="/checkin/{classroom_id}/view-records">签到记录</button>
  </form>

  {control_buttons}
  <!-- 添加新按钮 -->
  <form method="GET" action="/checkin/{classroom_id}/view-by-student">
    <button type="submit" class="btn btn-view">按学号查看签到情况</button>
  </form>
  <form method="POST" action="/checkin/{classroom_id}/reset" onsubmit="return confirm('确定要重置所有数据吗？此操作不可恢复！');">
    <input type="hidden" name="action" value="reset">
    <button type="submit" class="btn btn-reset">重置</button>
  </form>
  </div>
</body>
</html>'''

    def _render_admin(self, table_html='', classroom_id=''):
        """动态生成 admin 页面"""
        # 判断签到状态
        is_checkin_active = CheckinHandler.checkin_enabled.get(classroom_id, False)
        status_text = "正在签到..." if is_checkin_active else "未开始签到"
        
        # 生成控制按钮
        if is_checkin_active:
            control_buttons = '''
  <form method="POST" action="/checkin/{classroom_id}/stop-checkin">
    <button type="submit" class="btn btn-stop">结束签到</button>
  </form>'''.format(classroom_id=classroom_id)
        else:
            control_buttons = '''
  <form method="POST" action="/checkin/{classroom_id}/start-checkin">
    <button type="submit" class="btn btn-start">开始签到</button>
  </form>'''.format(classroom_id=classroom_id)


        html = self._admin_template.format(
            table_html=table_html,
            classroom_id=classroom_id,
            status_text=status_text,
            control_buttons=control_buttons
        )
        return html.encode('utf-8')

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

    def _build_table_html(self, classroom_id):
        """基于内存配置构建表格"""
        classroom_id, row, col = self._get_room_config(classroom_id)  # ✅ 接收 id
        if not classroom_id:
            return "<h2>配置错误</h2>"
        
        row = row or 4
        col = col or 12
        
        # 从 checkin-temp 表读取签到数据
        from .database import get_temp_checkins_by_classroom
        temp_checkins = get_temp_checkins_by_classroom(classroom_id)
        
        # 构建表格
        table = [["" for _ in range(col)] for _ in range(row)]
        for name, seat_number in temp_checkins:
            try:
                idx = seat_number - 1
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
    
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        # ✅ 修改路由: /checkin/manage.html
        if path == "/checkin/manage.html":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self._render_manage())
            return

        # 新增：提供 qrcode 目录下的静态文件（PDF/PNG）
        qr_match = re.match(r'^/checkin/(\d{3,4})/qrcode/(.+)$', path)
        if qr_match:
            classroom_id = qr_match.group(1)
            filename = qr_match.group(2)
            
            # 安全校验：只允许 .pdf 和 .png
            if not (filename.endswith('.pdf') or filename.endswith('.png')):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden: Invalid file type")
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
                        <span><strong>{cls["class"]}</strong> ({cls["count"]} 名学生)</span>
                        <button class="delete-btn" onclick="parent.deleteClass('{cls["class"]}')">删除班级</button>
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

        # 新增：按学号查看签到情况
        student_view_match = re.match(r'^/checkin/(\d{3,4})/view-by-student$', path)
        if student_view_match:
            classroom_id = student_view_match.group(1)
            
            # 获取该教室对应的班级名称
            from .database import get_class_name_by_classroom
            class_name = get_class_name_by_classroom(classroom_id)
            
            from .database import get_students_by_class_name, get_temp_checkins_with_ids_by_classroom
            all_students = get_students_by_class_name(class_name)

            # 获取该教室的临时签到数据（包含学号）
            temp_checkins = get_temp_checkins_with_ids_by_classroom(classroom_id)
            
            # 创建签到状态字典（使用学号作为键）
            checkin_status = {student_id: "未签" for student_id, _ in all_students}
            for student_id, _, _ in temp_checkins:  # 现在包含学号
                if student_id in checkin_status:
                    checkin_status[student_id] = "已签"
            
            # 生成HTML表格
            table_html = "<table border='1' style='width:100%; border-collapse: collapse;'>"
            table_html += "<tr><th>学号</th><th>姓名</th><th>签到状态</th></tr>"
            
            for student_id, name in all_students:
                status = checkin_status.get(student_id, "未签")
                table_html += f"<tr><td>{student_id}</td><td>{name}</td><td>{status}</td></tr>"
            
            table_html += "</table>"
            
            # 生成完整页面
            html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>按学号查看签到情况</title>
  <style>
    body {{ font-family: sans-serif; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ padding: 10px; text-align: left; border: 1px solid #ddd; }}
    th {{ background-color: #f2f2f2; }}
    .btn {{ display: inline-block; margin-top: 20px; padding: 10px 20px; 
           background-color: #4CAF50; color: white; text-decoration: none; border-radius: 4px; }}
    .btn:hover {{ background-color: #45a049; }}
  </style>
</head>
<body>
  <h2>教室 {classroom_id} 学生签到情况</h2>
  {table_html}
  <a href="/checkin/{classroom_id}/admin.html" class="btn">返回管理页面</a>
</body>
</html>"""
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("<h2>无效路径，请通过 /checkin/{教室ID}/admin.html 访问</h2>".encode('utf-8'))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        # 新增：删除签到记录
        if path == "/checkin/delete-record":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            course = params.get("course", [""])[0]
            save_time = params.get("save_time", [""])[0]
            classroom_id = params.get("classroom_id", [""])[0]
            
            # 调用数据库函数删除记录
            from .database import delete_checkin_record
            if delete_checkin_record(course, save_time, classroom_id):
                # 重新查询记录以刷新页面
                from .database import get_checkin_summary_by_course
                records = get_checkin_summary_by_course(course)
                
                # 重新渲染页面
                if records:
                    table_rows = ""
                    for record in records:
                        table_rows += f"""
                    <tr>
                        <td>{record['course']}</td>
                        <td>{record['classroom_id']}</td>
                        <td>{record['count']}</td>
                        <td>{record['save_time']}</td>
                        <td>
                            <form method="POST" action="/checkin/delete-record" style="display:inline;">
                                <input type="hidden" name="course" value="{record['course']}">
                                <input type="hidden" name="save_time" value="{record['save_time']}">
                                <input type="hidden" name="classroom_id" value="{record['classroom_id']}">
                                <button type="submit" class="btn-delete">删除记录</button>
                            </form>
                        </td>
                    </tr>"""
                    table_html = f"""
                <table class="record-table">
                    <tr>
                        <th>课程名称</th>
                        <th>教室ID</th>
                        <th>签到人数</th>
                        <th>保存时间</th>
                        <th>操作</th>
                    </tr>
                    {table_rows}
                </table>"""
                else:
                    table_html = "<p>未找到相关签到记录</p>"
                
                html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>签到记录</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}}
.container {{
    max-width: 800px;
    margin: 0 auto;
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}}
.record-table {{
    width: 100%;
    margin-top: 20px;
    border: 1px solid #ddd;
    border-collapse: collapse;
}}
.record-table th, .record-table td {{
    padding: 10px;
    text-align: left;
    border: 1极线 solid #ddd;
}}
.record-table th {{
    background-color: #f2f2f2;
}}
.btn {{
    display: inline-block;
    margin-top: 20px;
    padding: 10px 20px;
    background-color: #4CAF50;
    color: white;
    text-decoration: none;
    border-radius: 4px;
}}
.btn:hover {{
    background-color: #45a049;
}}
.btn-delete {{
    padding: 5px 10px; 
    background: #f44336; 
    color: white; 
    border: none; 
    cursor: pointer; 
    border-radius: 4px;
}}
</style>
</head>
<body>
  <div class="container">
    <h2>签到记录</h2>
    {table_html}
    <a href="/checkin/{classroom_id}/admin.html" class="btn">返回管理页面</a>
  </div>
</body>
</html>"""
            else:
                html_resp = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>删除失败</title></head>
<body>
<h2>删除失败</h2>
<p>记录删除失败，请重试。</p>
<p><a href="/checkin/manage.html">返回管理页面</a></p>
</body></html>"""
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        # ✅ 查看签到记录
        record_match = re.match(r'^/checkin/(\d{3,4})/view-records$', path)
        if record_match:
            classroom_id = record_match.group(1)
            # 获取课程名称
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            course_name = params.get("course", [""])[0]
            
            if not course_name:
                html_resp = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>查询失败</title></head>
<body><p>请输入课程名称</p><p><a href="/checkin/{classroom_id}/admin.html">返回</a></p></body></html>""".format(classroom_id=classroom_id)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html_resp.encode('utf-8'))
                return
            
            # 查询签到记录
            from .database import get_checkin_summary_by_course
            records = get_checkin_summary_by_course(course_name)
            
            # 生成记录表格
            if records:
                table_rows = ""
                for record in records:
                    table_rows += f"""
                <tr>
                    <td>{record['course']}</td>
                    <td>{record['classroom_id']}</td>
                    <td>{record['count']}</td>
                    <td>{record['save_time']}</td>
                    <td>
                        <form method="POST" action="/checkin/delete-record" style="display:inline;">
                            <input type="hidden" name="course" value="{record['course']}">
                            <input type="hidden" name="save_time" value="{record['save_time']}">
                            <input type="hidden" name="classroom_id" value="{record['classroom_id']}">
                            <button type="submit" class="btn-delete">删除记录</button>
                        </form>
                    </td>
                </tr>"""
                table_html = f"""
            <table class="record-table">
                <tr>
                    <th>课程名称</th>
                    <th>教室ID</th>
                    <th>签到人数</th>
                    <th>保存时间</th>
                    <th>操作</th>
                </tr>
                {table_rows}
            </table>"""
            else:
                table_html = "<p>未找到相关签到记录</p>"
            
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>签到记录</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}}
.container {{
    max-width: 800px;
    margin: 0 auto;
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}}
.record-table {{
    width: 100%;
    margin-top: 20px;
    border: 1px solid #ddd;
    border-collapse: collapse;
}}
.record-table th, .record-table td {{
    padding: 10px;
    text-align: left;
    border: 1px solid #ddd;
}}
.record-table th {{
    background-color: #f2f2f2;
}}
.btn {{
    display: inline-block;
    margin-top: 20px;
    padding: 10px 20px;
    background-color: #4CAF50;
    color: white;
    text-decoration: none;
    border-radius: 4px;
}}
.btn:hover {{
    background-color: #45a049;
}}
.btn-delete {{
    padding: 5px 10px; 
    background: #f44336; 
    color: white; 
    border: none; 
    cursor: pointer; 
    border-radius: 4px;
}}
</style>
</head>
<body>
  <div class="container">
    <h2>签到记录</h2>
    {table_html}
    <a href="/checkin/{classroom_id}/admin.html" class="btn">返回管理页面</a>
  </div>
</body>
</html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

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
            self.send_header('Location', "/checkin/manage/list")
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

        # 新增：删除指定班级的学生名单
        if path == "/checkin/manage/delete-class-students":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            
            class_name = params.get("class_name", [""])[0]
            if not class_name:
                self._send_import_result("班级名称不能为空", success=False)
                return

            deleted_count = delete_students_by_class_name(class_name)
            
            if deleted_count > 0:
                message = f"成功删除班级 '{class_name}' 中的 {deleted_count} 名学生"
            else:
                message = f"班级 '{class_name}' 不存在或无学生可删除"
                
            self._send_import_result(message)
            return

        # ✅ 匹配 /checkin/{id}/save 和 /checkin/{id}/reset
        save_match = re.match(r'^/checkin/(\d{3,4})/save$', path)
        reset_match = re.match(r'^/checkin/(\d{3,4})/reset$', path)

        if save_match:
            classroom_id = save_match.group(1)
            # 获取课程名称
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(body)
            course_name = params.get("course", [""])[0]
            
            # 保存到数据库
            from .database import save_checkin_records
            count = save_checkin_records(classroom_id, course_name)
            
            redirect_url = f"/checkin/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>保存成功</title>
<meta http-equiv="refresh" content="2;url={redirect_url}"></head>
<body><p>已保存 {count} 条签到记录，2秒后返回...</p></body></html>"""
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

        # ✅ 开始签到
        start_match = re.match(r'^/checkin/(\d{3,4})/start-checkin$', path)
        if start_match:
            classroom_id = start_match.group(1)
            CheckinHandler.checkin_enabled[classroom_id] = True
            redirect_url = f"/checkin/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>签到已开始</title>
<meta http-equiv="refresh" content="1;url={redirect_url}"></head>
<body><p>签到已开始，学生可以扫码签到。</p></body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        # ✅ 结束签到
        stop_match = re.match(r'^/checkin/(\d{3,4})/stop-checkin$', path)
        if stop_match:
            classroom_id = stop_match.group(1)
            CheckinHandler.checkin_enabled[classroom_id] = False
            redirect_url = f"/checkin/{classroom_id}/admin.html"
            html_resp = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>签到已结束</title>
<meta http-equiv="refresh" content="1;url={redirect_url}"></head>
<body><p>签到已结束，学生无法继续签到。</p></body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_resp.encode('utf-8'))
            return

        # Handle check-in POST: /checkin/{id}/checkin-XX.html
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        content_type = self.headers.get('Content-Type', '')

        student_id = None
        if 'application/json' in content_type:
            try:
                data = json.loads(body.decode('utf-8'))
                student_id = data.get('student_id') or data.get('user_id')
            except json.JSONDecodeError:
                student_id = None
        else:
            try:
                parsed = urllib.parse.parse_qs(body.decode('utf-8'))
                student_id = parsed.get('student_id', [None])[0]
            except Exception:
                student_id = None

        if student_id:
            # 提取 classroom_id 和 seq
            class_match = re.match(r'^/checkin/(\d{3,4})/checkin-(\d{2})\.html$', path)
            if not class_match:
                self.send_response(400)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h2>签到请求路径无效，请通过二维码访问</h2>".encode('utf-8'))
                return

            classroom_id = class_match.group(1)
            seq = int(class_match.group(2))

            # 检查是否允许签到
            if not CheckinHandler.checkin_enabled.get(classroom_id, False):
                message = "签到未开始或已结束"
                status = 403
            else:
                # 查询数据库获取姓名
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM students WHERE student_id = ?", (student_id,))
                row = cursor.fetchone()
                conn.close()

                if not row:
                    message = "学号未找到，请确认是否已导入名单"
                    status = 400
                else:
                    name = row[0]
                    # 保存到 checkin-temp 表
                    from .database import add_temp_checkin
                    if add_temp_checkin(student_id, classroom_id, seq):
                        message = f"签到成功：{name}"
                        status = 200
                    else:
                        message = "签到失败"
                        status = 500
        else:
            message = "缺少学号"
            status = 400

        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(self._render_form(message=message))

        # ✅ 重置操作
        reset_match = re.match(r'^/checkin/(\d{3,4})/reset$', path)
        if reset_match:
            classroom_id = reset_match.group(1)
            # 清空 checkin-temp 表中的数据
            from .database import clear_temp_checkins
            clear_temp_checkins(classroom_id)
            
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
