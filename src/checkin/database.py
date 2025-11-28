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
