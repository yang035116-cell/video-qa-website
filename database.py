import sqlite3
import json
from datetime import datetime

def init_db():
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    
    # 创建视频表
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         url TEXT UNIQUE,
         title TEXT,
         description TEXT,
         transcript TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    
    # 创建对话表
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         question TEXT,
         answer TEXT,
         video_id INTEGER,
         timestamp TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         FOREIGN KEY (video_id) REFERENCES videos (id))
    ''')
    
    conn.commit()
    conn.close()

def add_video(url, title, description, transcript):
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO videos (url, title, description, transcript)
            VALUES (?, ?, ?, ?)
        ''', (url, title, description, transcript))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # 视频已存在
        return False
    finally:
        conn.close()

def get_all_videos():
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    c.execute('SELECT * FROM videos ORDER BY created_at DESC')
    videos = c.fetchall()
    conn.close()
    return videos

def get_video_by_id(video_id):
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    c.execute('SELECT * FROM videos WHERE id = ?', (video_id,))
    video = c.fetchone()
    conn.close()
    return video

def add_conversation(question, answer, video_id, timestamp):
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO conversations (question, answer, video_id, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (question, answer, video_id, timestamp))
    conn.commit()
    conn.close()