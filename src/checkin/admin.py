import os
import html
import csv
import yaml
from datetime import datetime

def load_classroom_config(path=None, classroom_id=None):
    """
    Load classroom config from YAML file.
    If classroom_id is provided, return its config; else return first one.
    Returns: (room_number, row, column) or (None, None, None) if not found.
    """
    p = path or os.path.join(os.path.dirname(__file__), 'room_info.yaml')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        classrooms = data.get('classrooms', [])
        if classroom_id:
            for room in classrooms:
                if room.get('id') == classroom_id:
                    return (
                        room.get('room_number', classroom_id),
                        room.get('row', 4),
                        room.get('column', 12)
                    )
            return None, None, None
        else:
            # Return first classroom if no ID specified
            if classrooms:
                room = classrooms[0]
                return (
                    room.get('room_number', room.get('id', '1058')),
                    room.get('row', 4),
                    room.get('column', 12)
                )
            return '1058', 4, 12
    except Exception:
        return '1058', 4, 12

def build_table_html_from_namefile(name_file="name.txt", classroom_id=None, room_info_path=None):
    """
    Build HTML table for a specific classroom.
    """
    room_number, row, column = load_classroom_config(room_info_path, classroom_id)
    if room_number is None:
        return "<h2>教室配置未找到</h2>"

    # Ensure row and column are integers with defaults
    row = row or 4
    column = column or 12

    # ✅ 如果传入了 classroom_id，自动使用 name-{id}.txt
    if classroom_id and not name_file.startswith("name-"):
        name_file = f"name-{classroom_id}.txt"

    # ✅ 所有文件路径统一加 data/ 前缀
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    name_file = os.path.join(data_dir, name_file)

    entries = {}
    if os.path.exists(name_file):
        with open(name_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2:
                    prefix, name = parts[0], parts[1]
                    entries[prefix] = name

    # Build table (inverted row order for display)
    table = [["" for _ in range(column)] for _ in range(row)]
    for prefix_str, name in entries.items():
        try:
            prefix = int(prefix_str)
            r_idx = (prefix - 1) // column
            c_idx = (prefix - 1) % column
            if 0 <= r_idx < row and 0 <= c_idx < column:
                table[row - 1 - r_idx][c_idx] = name
        except ValueError:
            continue

    table_html = "<table border='1' style='width:100%; border-collapse: collapse;'>\n"
    for tr in table:
        table_html += "  <tr>\n"
        for cell in tr:
            escaped_cell = html.escape(cell) if cell else "&nbsp;"
            table_html += f"    <td style='padding:8px; text-align:center;'>{escaped_cell}</td>\n"
        table_html += "  </tr>\n"
    table_html += "</table>"
    return table_html

def save_csv_to_dir(name_file="name.txt", out_dir=None, classroom_id=None, room_info_path=None):
    """
    Save CSV for a specific classroom.
    """
    room_number, row, column = load_classroom_config(room_info_path, classroom_id)
    if room_number is None:
        return "ERROR: Classroom config not found"

    # Ensure row and column are integers with defaults
    row = row or 4
    column = column or 12

    # ✅ 如果传入了 classroom_id，自动使用 name-{id}.txt
    if classroom_id and not name_file.startswith("name-"):
        name_file = f"name-{classroom_id}.txt"

    # ✅ 所有文件路径统一加 data/ 前缀
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    name_file = os.path.join(data_dir, name_file)

    entries = {}
    if os.path.exists(name_file):
        with open(name_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2:
                    prefix, name = parts[0], parts[1]
                    entries[prefix] = name

    table = [["" for _ in range(column)] for _ in range(row)]
    for prefix_str, name in entries.items():
        try:
            prefix = int(prefix_str)
            r_idx = (prefix - 1) // column
            c_idx = (prefix - 1) % column
            if 0 <= r_idx < row and 0 <= c_idx < column:
                table[r_idx][c_idx] = name
        except ValueError:
            continue

    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    csv_filename = f"checkin-{room_number}-{timestamp}.csv"
    out_dir = out_dir or data_dir  # ✅ 默认输出到 data/ 目录
    csv_path = os.path.join(out_dir, csv_filename)

    with open(csv_path, "w", encoding="utf-8", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(table)

    return csv_filename

def reset_namefile(name_file="name.txt", classroom_id=None):
    # ✅ 如果传入了 classroom_id，自动使用 data/name-{id}.txt
    if classroom_id:
        name_file = f"name-{classroom_id}.txt"

    # ✅ 所有文件路径统一加 data/ 前缀
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    name_file = os.path.join(data_dir, name_file)

    if os.path.exists(name_file):
        try:
            print(f"Deleting: {name_file}")  # ✅ 调试用
            os.remove(name_file)
            return True
        except Exception as e:
            print(f"Failed to delete {name_file}: {e}")
            return False
    return True

if __name__ == "__main__":
    # Test: save CSV using default room_info.yaml and first classroom
    fn = save_csv_to_dir(classroom_id=None, room_info_path=None)
    print("Saved:", fn)