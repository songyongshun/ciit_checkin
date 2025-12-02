import sqlite3

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
    # 创建 checkin 表 - 添加 classroom_id 字段, 默认状态改为"缺勤"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '缺勤',
            save_time TEXT NOT NULL,
            class_name TEXT NOT NULL,
            name TEXT NOT NULL,
            course TEXT,
            classroom_id TEXT NOT NULL,  
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    # 创建 checkin-temp 表（临时存储签到数据）, 默认状态改为"缺勤"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "checkin-temp" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '缺勤',
            class_name TEXT NOT NULL,
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
    return [{"class": r[0], "count": r[1]} for r in rows]


def delete_students_by_class_name(class_name):
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
            SELECT student_id, status, class_name, name 
            FROM "checkin-temp" 
            WHERE classroom_id = ?
        """, (classroom_id,))
        temp_records = cursor.fetchall()

        if not temp_records:
            return 0  # 没有记录可保存

        # 2. 插入到 checkin 表（主记录表）- 添加 classroom_id 字段, 状态从temp表获取
        cursor.executemany("""
            INSERT INTO checkin 
            (student_id, status, save_time, class_name, name, course, classroom_id) 
            VALUES (?, ?, datetime('now', 'localtime'), ?, ?, ?, ?)
        """, [
            (row[0], row[1], row[2], row[3], course_name, classroom_id)  # row[1] is status from temp table
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
    """根据课程名称获取签到记录汇总（包含详细状态统计）"""
    if not course_name:
        return []
        
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 查询同一save_time下的签到记录详细统计，包含class_name
    cursor.execute("""
        SELECT 
            course, 
            classroom_id,
            class_name,
            save_time,
            SUM(CASE WHEN status = '已签' THEN 1 ELSE 0 END) as signed,
            SUM(CASE WHEN status = '事假' THEN 1 ELSE 0 END) as personal_leave,
            SUM(CASE WHEN status = '病假' THEN 1 ELSE 0 END) as sick_leave,
            SUM(CASE WHEN status = '公假' THEN 1 ELSE 0 END) as official_leave,
            SUM(CASE WHEN status = '缺勤' THEN 1 ELSE 0 END) as absent,
            SUM(CASE WHEN status = '迟到' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN status = '早退' THEN 1 ELSE 0 END) as early_leave
        FROM checkin 
        WHERE course = ? 
        GROUP BY save_time, course, classroom_id, class_name  
        ORDER BY save_time DESC
    """, (course_name,))
    
    rows = cursor.fetchall()
    
    # 获取班级总人数
    results = []
    for row in rows:
        course, classroom_id, class_name, save_time, signed, personal_leave, sick_leave, official_leave, absent, late, early_leave = row
        
        # 获取该班级的总学生数
        class_student_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM students WHERE class_name = ?", (class_name,))
            count_row = cursor.fetchone()
            if count_row:
                class_student_count = count_row[0]
        except Exception:
            pass
        
        results.append({
            "course": course,
            "classroom_id": classroom_id,
            "class_total": class_student_count,
            "signed": signed or 0,
            "personal_leave": personal_leave or 0,
            "sick_leave": sick_leave or 0,
            "official_leave": official_leave or 0,
            "absent": absent or 0,
            "late": late or 0,
            "early_leave": early_leave or 0,
            "save_time": save_time
        })
    
    conn.close()
    return results


def get_temp_checkins_by_classroom(classroom_id):
    """获取指定教室的临时签到数据"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, seat_number 
        FROM "checkin-temp" 
        WHERE classroom_id = ? AND status = '已签'
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


def add_temp_checkin(student_id, classroom_id, seat_number, status="已签"):
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
        (student_id, status, class_name, name, seat_number, classroom_id) 
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (student_id, status, class_name, name, seat_number, classroom_id))
    
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


def get_students_by_classroom(classroom_id):
    """获取指定教室的所有学生信息（包括学号、姓名和班级）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    # 查询临时签到表中的学生信息
    cursor.execute('''
        SELECT student_id, name, class_name, status
        FROM "checkin-temp"
        WHERE classroom_id = ?
    ''', (classroom_id,))
    students = cursor.fetchall()
    conn.close()
    return students


def get_students_by_class_name(class_name):
    """获取指定班级的所有学生"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, name FROM students WHERE class_name = ?", (class_name,))
    students = cursor.fetchall()
    conn.close()
    return students


def get_class_name_by_classroom(classroom_id):
    """获取教室对应的班级名称"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''SELECT DISTINCT class_name FROM "checkin-temp" WHERE classroom_id = ?''', (classroom_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""


def get_temp_checkins_with_ids_by_classroom(classroom_id):
    """获取指定教室的临时签到数据（包含学号和状态）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT student_id, name, seat_number, status
        FROM "checkin-temp" 
        WHERE classroom_id = ? 
        ORDER BY seat_number
    """, (classroom_id,))
    rows = cursor.fetchall()
    conn.close()
    return [(row[0], row[1], row[2], row[3]) for row in rows]