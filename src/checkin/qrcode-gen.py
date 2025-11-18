import qrcode
from PIL import ImageDraw, ImageFont
import argparse
from . import server, admin  # ✅ 导入 admin 模块


# ✅ 获取默认教室编号用于提示
room_number, _, _ = admin.load_classroom_config(config)
if room_number is None:
    room_number = "1058"  # fallback

base_url = "http://47.103.9.15/checkin/{room_number}/checkin-{}.py"

for num in range(1, 49):
  url = base_url.format(str(num).zfill(2))
  qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
  )
  qr.add_data(url)
  qr.make(fit=True)
  img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
  
  # Add text in the center
  draw = ImageDraw.Draw(img)
  try:
    font = ImageFont.truetype("arial.ttf", 20)
  except IOError:
    font = ImageFont.load_default()
  
  text = str(num).zfill(2)
  text_bbox = draw.textbbox((0, 0), text, font=font)
  text_width = text_bbox[2] - text_bbox[0]
  text_height = text_bbox[3] - text_bbox[1]
  img_width, img_height = img.size
  position = ((img_width - text_width) // 2, 5)  # Top with 5px margin
  draw.text(position, text, font=font, fill="black")
  
  img.save(f"qr8-{str(num).zfill(2)}.png")
