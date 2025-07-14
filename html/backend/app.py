import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import uuid
import logging
import time
import threading
import functools

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, static_folder='../uploads')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../uploads')
CORS(app)

# 配置文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')  # 修正上传路径
DB_PATH = os.path.join(BASE_DIR, 'homework.db')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
logging.info(f"上传目录设置为: {UPLOAD_FOLDER}")

# 数据库锁机制
db_lock = threading.Lock()

def get_db_connection():
    conn = None
    attempts = 0
    max_attempts = 5
    
    while attempts < max_attempts:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            return conn
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempts < max_attempts - 1:
                logging.warning(f"数据库被锁定，重试中... ({attempts+1}/{max_attempts})")
                time.sleep(0.5)
                attempts += 1
            else:
                logging.error(f"无法连接数据库: {e}")
                raise

def init_db():
    with db_lock:
        conn = get_db_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS homeworks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    homework_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    FOREIGN KEY (homework_id) REFERENCES homeworks (id)
                )
            ''')
            conn.commit()
        finally:
            conn.close()

# 带锁的数据库操作装饰器
def with_db_lock(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with db_lock:
            return func(*args, **kwargs)
    return wrapper

@app.route('/api/homeworks', methods=['GET'])
@with_db_lock
def get_homeworks():
    conn = get_db_connection()
    try:
        homeworks = conn.execute('SELECT * FROM homeworks ORDER BY created_at DESC').fetchall()
        attachments = conn.execute('SELECT * FROM attachments').fetchall()
        
        # 按科目分组
        data = {}
        for hw in homeworks:
            subject = hw['subject']
            if subject not in data:
                data[subject] = {"homeworks": []}
            
            hw_attachments = [att for att in attachments if att['homework_id'] == hw['id']]
            
            homework = {
                'id': hw['id'],
                'time': hw['time'],
                'subject': subject,
                'title': hw['title'],
                'content': hw['content'],
                'createdAt': hw['created_at'],
                'attachments': [
                    {
                        'id': att['id'],
                        'filename': att['filename'],
                        'filepath': att['filepath']
                    } for att in hw_attachments
                ]
            }
            data[subject]["homeworks"].append(homework)
            
        return jsonify(data)
    finally:
        conn.close()

@app.route('/api/homeworks', methods=['POST'])
@with_db_lock
def add_homework():
    data = request.form
    files = request.files.getlist('attachments')
    
    logging.info(f"收到添加作业请求: {data}")
    logging.info(f"包含 {len(files)} 个附件")

    # 验证必填字段
    required_fields = ['time', 'subject', 'title', 'content']
    if not all(field in data for field in required_fields):
        return jsonify({'error': '缺少必填字段'}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            'INSERT INTO homeworks (time, subject, title, content) VALUES (?, ?, ?, ?)',
            (data['time'], data['subject'], data['title'], data['content'])
        )
        homework_id = cursor.lastrowid

        # 保存附件
        saved_files = []
        for file in files:
            if file.filename == '':
                continue
            
            # 生成唯一文件名
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}_{file.filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            file.save(file_path)
            logging.info(f"保存附件: {file.filename} -> {file_path}")
            
            # 保存到数据库
            conn.execute(
                'INSERT INTO attachments (homework_id, filename, filepath) VALUES (?, ?, ?)',
                (homework_id, file.filename, unique_filename)
            )
            saved_files.append({
                'filename': file.filename,
                'filepath': unique_filename
            })
        
        conn.commit()
        
        return jsonify({
            'id': homework_id,
            'message': '作业添加成功',
            'attachments': saved_files
        }), 201
    except Exception as e:
        logging.error(f"添加作业失败: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500
    finally:
        conn.close()

@app.route('/api/homeworks/<int:id>', methods=['PUT'])
@with_db_lock
def update_homework(id):
    data = request.form
    files = request.files.getlist('attachments')
    
    logging.info(f"收到更新作业请求 (ID: {id}): {data}")
    logging.info(f"包含 {len(files)} 个附件")

    # 验证必填字段
    required_fields = ['time', 'subject', 'title', 'content']
    if not all(field in data for field in required_fields):
        return jsonify({'error': '缺少必填字段'}), 400

    conn = get_db_connection()
    try:
        # 检查作业是否存在
        homework = conn.execute('SELECT * FROM homeworks WHERE id = ?', (id,)).fetchone()
        if homework is None:
            return jsonify({'error': '作业未找到'}), 404

        # 更新作业基本信息
        conn.execute(
            'UPDATE homeworks SET time=?, subject=?, title=?, content=? WHERE id=?',
            (data['time'], data['subject'], data['title'], data['content'], id)
        )
        
        # 保存新附件
        saved_files = []
        for file in files:
            if file.filename == '':
                continue
            
            # 生成唯一文件名
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}_{file.filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            file.save(file_path)
            logging.info(f"保存新附件: {file.filename} -> {file_path}")
            
            # 保存到数据库
            conn.execute(
                'INSERT INTO attachments (homework_id, filename, filepath) VALUES (?, ?, ?)',
                (id, file.filename, unique_filename)
            )
            saved_files.append({
                'filename': file.filename,
                'filepath': unique_filename
            })
        
        conn.commit()
        
        return jsonify({
            'id': id,
            'message': '作业更新成功',
            'attachments': saved_files
        })
    except Exception as e:
        logging.error(f"更新作业失败: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500
    finally:
        conn.close()

@app.route('/api/homeworks/<int:id>', methods=['DELETE'])
@with_db_lock
def delete_homework(id):
    logging.info(f"收到删除作业请求 (ID: {id})")
    
    conn = get_db_connection()
    try:
        # 获取附件列表
        attachments = conn.execute(
            'SELECT id, filepath FROM attachments WHERE homework_id = ?', (id,)
        ).fetchall()
        
        # 删除数据库记录
        conn.execute('DELETE FROM attachments WHERE homework_id = ?', (id,))
        conn.execute('DELETE FROM homeworks WHERE id = ?', (id,))
        conn.commit()
        
        # 删除文件
        for att in attachments:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], att['filepath'])
            if os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                    logging.info(f"删除附件: {file_path}")
                except Exception as e:
                    logging.error(f"删除文件失败: {e}")
        
        logging.info(f"作业 ID:{id} 已删除")
        
        return jsonify({'message': '作业已删除'})
    except Exception as e:
        logging.error(f"删除作业失败: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500
    finally:
        conn.close()

@app.route('/uploads/<path:filename>')  # 移除了/api前缀
def uploaded_file(filename):
    # 使用配置的上传文件夹路径
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    logging.info(f"文件请求: {filename} -> {file_path}")
    
    if not os.path.exists(file_path):
        logging.error(f"文件未找到: {file_path}")
        return jsonify({"error": "文件未找到"}), 404
    
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logging.error(f"发送文件失败: {str(e)}")
        return jsonify({"error": "文件发送失败"}), 500

# 错误处理
@app.errorhandler(500)
def internal_error(error):
    logging.error(f"服务器错误: {error}")
    return jsonify({"error": "服务器内部错误"}), 500

@app.errorhandler(404)
def not_found(error):
    logging.error(f"未找到资源: {request.url}")
    return jsonify({"error": "资源未找到"}), 404

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
