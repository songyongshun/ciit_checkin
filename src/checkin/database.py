import sqlite3
import datetime

DATABASE_PATH = "checkin.db"


def init_database():
    """初始化数据库，创建 classrooms、students 和 checkin 表"""
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
    # 创建 checkin 表 - 添加 classroom_id 字段
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '正常',
            save_time TEXT NOT NULL,
            class TEXT NOT NULL,
            name TEXT NOT NULL,
            course TEXT,
            classroom_id TEXT NOT NULL,  
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    # 创建 checkin-temp 表（临时存储签到数据）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "checkin-temp" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '正常',
            class TEXT NOT NULL,
            name TEXT NOT NULL,
            seat_number INTEGER,
            classroom_id TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
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


def save_checkin_records(classroom_id, course_name):
    """将 checkin-temp 表中的临时签到记录写入 checkin 表，但不清空临时表"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        # 开始事务
        conn.execute("BEGIN")

        # 1. 从 checkin-temp 获取该教室的所有签到记录
        cursor.execute("""
            SELECT student_id, name, seat_number 
            FROM "checkin-temp" 
            WHERE classroom_id = ?
        """, (classroom_id,))
        temp_records = cursor.fetchall()

        if not temp_records:
            return 0  # 没有记录可保存

        # 2. 插入到 checkin 表（主记录表）- 添加 classroom_id 字段
        cursor.executemany("""
            INSERT INTO checkin 
            (student_id, status, save_time, class, name, course, classroom_id) 
            VALUES (?, ?, datetime('now', 'localtime'), ?, ?, ?, ?)
        """, [
            (row[0], "正常", row[1].split('-')[0] if '-' in row[1] else "未知班级", 
             row[1], course_name, classroom_id)  # 添加 classroom_id
            for row in temp_records
        ])

        conn.commit()
        return len(temp_records)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_checkin_summary_by_course(course_name):
    """根据课程名称获取签到记录汇总"""
    if not course_name:
        return []
        
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 查询同一save_time下的签到记录汇总 - 添加 classroom_id
    cursor.execute("""
        SELECT course, COUNT(*) as count, save_time, classroom_id 
        FROM checkin 
        WHERE course = ? 
        GROUP BY save_time, course, classroom_id  
        ORDER BY save_time DESC
    """, (course_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # 返回结果中包含教室ID
    return [{"course": r[0], "count": r[1], "save_time": r[2], "classroom_id": r[3]} for r in rows]


def get_temp_checkins_by_classroom(classroom_id):
    """获取指定教室的临时签到数据"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, seat_number 
        FROM "checkin-temp" 
        WHERE classroom_id = ? 
        ORDER BY seat_number
    """, (classroom_id,))
    rows = cursor.fetchall()
    conn.close()
    return [(row[0], row[1]) for row in rows]


def clear_temp_checkins(classroom_id):
    """清空指定教室的临时签到数据"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM "checkin-temp" WHERE classroom_id = ?', (classroom_id,))
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def add_temp_checkin(student_id, classroom_id, seat_number):
    """添加临时签到记录"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    # 先查询学生信息
    cursor.execute("SELECT name, class_name FROM students WHERE student_id = ?", (student_id,))
    student_row = cursor.fetchone()
    if not student_row:
        conn.close()
        return False
    
    name, class_name = student_row
    # 插入临时签到记录
    cursor.execute('''
        INSERT OR REPLACE INTO "checkin-temp" 
        (student_id, status, class, name, seat_number, classroom_id) 
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (student_id, "正常", class_name, name, seat_number, classroom_id))
    
    conn.commit()
    conn.close()
    return True


def delete_checkin_record(course, save_time, classroom_id):
    """删除指定签到记录"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM checkin 
            WHERE course = ? 
            AND save_time = ? 
            AND classroom_id = ?
        """, (course, save_time, classroom_id))
        count = cursor.rowcount
        conn.commit()
        return count > 0
    except Exception as e:
        print(f"Error deleting record: {e}")
        return False
    finally:
        conn.close()
