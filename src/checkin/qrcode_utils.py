import os
import subprocess
import qrcode
from qrcode.constants import ERROR_CORRECT_L
import qrcode.image.pil as qrcode_image_pil
from PIL import ImageDraw, ImageFont

def generate_qr_codes(handler, classroom_id):
    """
    handler: CheckinHandler 实例（用于调用 handler._get_room_config 和 handler.public_ip）
    classroom_id: 教室 id 字符串
    返回: True / False
    """
    classroom_id, row, col = handler._get_room_config(classroom_id)
    if not classroom_id:
        return False

    public_ip = getattr(handler, 'public_ip', '127.0.0.1')
    total_seats = min(row * col, 48)

    output_dir = os.path.join("data", classroom_id, "qrcode")
    os.makedirs(output_dir, exist_ok=True)

    base_url = f"http://{public_ip}/checkin/{classroom_id}/checkin-{{:02d}}.html"

    for num in range(1, total_seats + 1):
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        # build the URL for this seat and add to the QR
        url = base_url.format(num)
        qr.add_data(url)
        qr.make(fit=True)
        # force use of the PIL image factory and extract the real PIL.Image.Image
        img = qr.make_image(fill_color="black", back_color="white", image_factory=qrcode_image_pil.PilImage).get_image().convert("RGB")

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()

        text = f"{num:02d}"
        # 计算文字宽度：优先使用 draw.textbbox（新接口），回退到 font.getbbox / font.getmask，
        # 最后以字体大小与字符数做近似估算。避免使用 draw.textsize 或 font.getsize（某些环境不可用）。
        try:
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
        except Exception:
            text_width = None
            # 优先尝试 font.getbbox（较新的 Pillow 接口）
            if hasattr(font, "getbbox"):
                try:
                    fb = font.getbbox(text)
                    text_width = fb[2] - fb[0]
                except Exception:
                    text_width = None
            # 回退到 font.getmask（更广泛可用），通过 mask.size 获取宽度
            if text_width is None and hasattr(font, "getmask"):
                try:
                    mask = font.getmask(text)
                    text_width = mask.size[0]
                except Exception:
                    text_width = None
            # 最后退回到近似估算：使用字体大小与字符数估算宽度
            if text_width is None:
                approx_char_width = getattr(font, "size", 12) * 0.6
                text_width = int(len(text) * approx_char_width)

        img_width, _ = img.size
        position = ((img_width - text_width) // 2, 5)
        draw.text(position, text, font=font, fill="black")

        filename = os.path.join(output_dir, f"qr-{num:02d}.png")
        img.save(filename)

    return True

def generate_latex_file(handler, classroom_id):
    """
    根据已有的 qr-*.png 生成 .tex 文件，返回 tex 文件路径或 None
    """
    classroom_id, row, col = handler._get_room_config(classroom_id)
    if not classroom_id:
        return None

    total_seats = min(row * col, 48)
    output_dir = os.path.join("data", classroom_id, "qrcode")

    for i in range(1, total_seats + 1):
        qr_file = os.path.join(output_dir, f"qr-{i:02d}.png")
        if not os.path.exists(qr_file):
            return None

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
    for i in range(1, total_seats + 1):
        latex_content += f"  \\includegraphics[width=0.23\\textwidth]{{qr-{i:02d}.png}}%\n"
        if i < total_seats:
            remainder = (i - 1) % 4
            if remainder == 3:
                latex_content += "  \\par\n"
            else:
                latex_content += "  \\hfill\n"

    latex_content += r"\end{document}"

    tex_file = os.path.join(output_dir, f"qrcode-{classroom_id}.tex")
    with open(tex_file, 'w', encoding='utf-8') as f:
        f.write(latex_content)

    return tex_file

def compile_latex_to_pdf(tex_file_path, timeout=30):
    """
    调用 pdflatex 编译 tex -> pdf，返回 pdf 路径或 None
    """
    try:
        tex_dir = os.path.dirname(tex_file_path)
        tex_filename = os.path.basename(tex_file_path)
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', tex_filename],
            cwd=tex_dir,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            pdf_file = tex_file_path.replace('.tex', '.pdf')
            if os.path.exists(pdf_file):
                return pdf_file
        else:
            # 失败时可在日志中打印 result.stderr
            return None
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None
