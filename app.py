from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
import openai
import re
import os
import httplib2
import socket
from database import init_db, add_video, get_all_videos, get_video_by_id, add_conversation
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# 初始化数据库
init_db()

# API配置 - 从环境变量获取，避免硬编码
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 检查API密钥是否设置
if not YOUTUBE_API_KEY:
    print("❌ 警告: YOUTUBE_API_KEY 未设置")
if not OPENAI_API_KEY:
    print("❌ 警告: OPENAI_API_KEY 未设置")

def create_http_with_timeout():
    """创建带超时的HTTP对象"""
    try:
        http = httplib2.Http(timeout=30)
        print("✅ HTTP对象创建成功")
        return http
    except Exception as e:
        print(f"❌ 创建HTTP对象失败: {e}")
        return httplib2.Http(timeout=30)

# 创建YouTube服务
if YOUTUBE_API_KEY:
    try:
        http = create_http_with_timeout()
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY, http=http)
        print("✅ YouTube API服务创建成功")
    except Exception as e:
        print(f"❌ YouTube API服务创建失败: {e}")
        youtube = None
else:
    youtube = None
    print("❌ YouTube API密钥未设置，视频相关功能不可用")

def extract_video_id(url):
    """提取视频ID"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([^"&?\/\s]{11})',
        r'(?:youtu\.be\/)([^"&?\/\s]{11})',
        r'(?:youtube\.com\/embed\/)([^"&?\/\s]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_info(url):
    """使用官方YouTube API获取完整视频信息"""
    if not youtube:
        print("❌ YouTube API服务未初始化")
        return None
        
    try:
        print(f"🚀 开始使用官方API获取视频信息: {url}")
        
        # 提取视频ID
        video_id = extract_video_id(url)
        if not video_id:
            print("❌ 无法提取视频ID")
            return None
        
        print(f"📹 视频ID: {video_id}")
        
        # 设置socket超时
        socket.setdefaulttimeout(30)
        
        # 使用YouTube Data API v3获取视频信息
        print("🔍 正在调用YouTube API...")
        
        # 获取视频基本信息
        video_response = youtube.videos().list(
            part='snippet,statistics,contentDetails',
            id=video_id
        ).execute()
        
        if not video_response['items']:
            print("❌ 未找到视频信息")
            return None
        
        video_data = video_response['items'][0]
        snippet = video_data['snippet']
        statistics = video_data['statistics']
        content_details = video_data['contentDetails']
        
        # 提取视频信息
        title = snippet['title']
        description = snippet['description']
        channel_title = snippet['channelTitle']
        published_at = snippet['publishedAt']
        view_count = statistics.get('viewCount', '0')
        like_count = statistics.get('likeCount', '0')
        duration = content_details['duration']
        
        # 解析ISO 8601时长格式 - 添加isodate导入
        try:
            import isodate
            duration_seconds = int(isodate.parse_duration(duration).total_seconds())
            duration_formatted = f"{duration_seconds // 60}:{duration_seconds % 60:02d}"
        except ImportError:
            print("❌ isodate库未安装，无法解析视频时长")
            duration_seconds = 0
            duration_formatted = "未知"
        except Exception:
            duration_seconds = 0
            duration_formatted = "未知"
        
        print(f"✅ 成功获取视频信息！")
        print(f"📺 视频标题: {title}")
        print(f"👤 频道: {channel_title}")
        print(f"⏱️ 时长: {duration_formatted} ({duration_seconds}秒)")
        print(f"👁️ 观看次数: {view_count}")
        print(f"👍 点赞数: {like_count}")
        print(f"📅 发布时间: {published_at}")
        print(f"📄 描述长度: {len(description)} 字符")
        
        # 获取字幕
        transcript = "无可用字幕"
        try:
            print("📝 正在获取字幕...")
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript = " ".join([item['text'] for item in transcript_list])
            print(f"✅ 成功获取字幕，长度: {len(transcript)} 字符")
        except Exception as e:
            print(f"❌ 字幕获取失败: {e}")
            # 使用视频描述作为替代
            transcript = description[:1000] if description else "无可用字幕"
            print("📄 使用视频描述作为替代")
        
        # 获取视频缩略图
        thumbnails = snippet['thumbnails']
        thumbnail_url = thumbnails.get('standard', thumbnails.get('high', thumbnails.get('medium', {}))).get('url', '')
        
        # 返回完整的视频信息
        video_info = {
            'title': title,
            'description': description[:500],
            'transcript': transcript,
            'channel_title': channel_title,
            'duration': duration_seconds,
            'view_count': int(view_count),
            'like_count': int(like_count),
            'published_at': published_at,
            'thumbnail_url': thumbnail_url,
            'video_url': f"https://www.youtube.com/watch?v={video_id}"
        }
        
        print(f"🎉 完整视频信息获取完成！")
        return video_info
            
    except HttpError as e:
        print(f"💥 YouTube API错误: {e}")
        if e.resp.status == 403:
            print("❌ API配额已用尽或API密钥无效")
        elif e.resp.status == 404:
            print("❌ 视频未找到")
        return None
    except socket.timeout:
        print("💥 网络连接超时，请检查网络连接")
        return None
    except Exception as e:
        print(f"💥 获取视频信息时发生错误: {str(e)}")
        import traceback
        print(f"🔍 详细错误信息: {traceback.format_exc()}")
        return None

def search_youtube_videos(keywords, max_results=50):
    """根据关键词搜索YouTube视频"""
    if not youtube:
        print("❌ YouTube API服务未初始化")
        return []
    
    try:
        all_videos = []
        
        for keyword in keywords:
            print(f"🔍 正在搜索关键词: {keyword}")
            
            # 搜索视频
            search_response = youtube.search().list(
                q=keyword,
                part='snippet',
                type='video',
                maxResults=max_results,
                order='viewCount'
            ).execute()
            
            # 获取视频详细信息
            video_ids = [item['id']['videoId'] for item in search_response['items']]
            
            if video_ids:
                videos_response = youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(video_ids)
                ).execute()
                
                for video in videos_response['items']:
                    snippet = video['snippet']
                    statistics = video['statistics']
                    content_details = video['contentDetails']
                    
                    # 计算点赞率
                    view_count = int(statistics.get('viewCount', 0))
                    like_count = int(statistics.get('likeCount', 0))
                    like_ratio = like_count / view_count if view_count > 0 else 0
                    
                    video_info = {
                        'video_id': video['id'],
                        'title': snippet['title'],
                        'description': snippet['description'],
                        'channel_title': snippet['channelTitle'],
                        'published_at': snippet['publishedAt'],
                        'view_count': view_count,
                        'like_count': like_count,
                        'like_ratio': like_ratio,
                        'duration': content_details['duration'],
                        'url': f"https://www.youtube.com/watch?v={video['id']}",
                        'keyword': keyword
                    }
                    all_videos.append(video_info)
        
        return all_videos
        
    except Exception as e:
        print(f"💥 搜索视频时发生错误: {e}")
        return []

def filter_high_quality_videos(videos, top_percent=25):
    """筛选优质视频（点赞量前25%）"""
    if not videos:
        return []
    
    # 按点赞数排序
    sorted_videos = sorted(videos, key=lambda x: x['like_count'], reverse=True)
    
    # 计算前25%的数量
    top_count = max(1, len(sorted_videos) * top_percent // 100)
    
    # 获取前25%的视频
    high_quality_videos = sorted_videos[:top_count]
    
    print(f"📊 视频统计:")
    print(f"   总视频数: {len(videos)}")
    print(f"   优质视频数（前{top_percent}%）: {len(high_quality_videos)}")
    if high_quality_videos:
        print(f"   最高点赞数: {high_quality_videos[0]['like_count']}")
        print(f"   最低点赞数（优质组）: {high_quality_videos[-1]['like_count']}")
    
    return high_quality_videos

def auto_build_video_library(keywords):
    """自动构建优质视频库"""
    print(f"🎯 开始自动构建视频库，关键词: {keywords}")
    
    # 搜索视频
    all_videos = search_youtube_videos(keywords)
    
    if not all_videos:
        print("❌ 未找到任何视频")
        return 0
    
    # 筛选优质视频
    high_quality_videos = filter_high_quality_videos(all_videos, 25)
    
    if not high_quality_videos:
        print("❌ 未找到优质视频")
        return 0
    
    added_count = 0
    
    # 处理每个优质视频
    for video_info in high_quality_videos:
        print(f"\n📹 处理优质视频: {video_info['title']}")
        print(f"   👍 点赞数: {video_info['like_count']}")
        print(f"   👁️ 观看数: {video_info['view_count']}")
        print(f"   🔑 关键词: {video_info['keyword']}")
        
        # 获取字幕
        transcript = "无可用字幕"
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_info['video_id'])
            transcript = " ".join([item['text'] for item in transcript_list])
            print(f"   ✅ 成功获取字幕")
        except Exception as e:
            print(f"   ❌ 字幕获取失败: {e}")
            transcript = video_info['description'][:1000] if video_info['description'] else "无可用字幕"
        
        # 添加到数据库
        success = add_video(
            video_info['url'],
            video_info['title'],
            video_info['description'][:500],
            transcript
        )
        
        if success:
            added_count += 1
            print(f"   💾 成功添加到视频库")
        else:
            print(f"   ❌ 添加失败（可能已存在）")
    
    print(f"\n🎉 自动构建完成！成功添加 {added_count} 个优质视频")
    return added_count

def search_videos(query):
    """优化搜索：使用SQLite的LIKE语句在数据库层面筛选"""
    conn = sqlite3.connect('video_qa.db')
    c = conn.cursor()
    
    try:
        # 使用SQL的LIKE进行模糊匹配，提高效率
        c.execute('''
            SELECT id, url, title, description, transcript, created_at 
            FROM videos 
            WHERE transcript LIKE ? 
            ORDER BY created_at DESC
        ''', (f'%{query}%',))
        
        videos = c.fetchall()
        results = []
        
        for video in videos:
            vid, url, title, description, transcript, created_at = video
            
            # 找到查询词在字幕中的位置
            start_idx = transcript.lower().find(query.lower())
            if start_idx == -1:
                continue
                
            context_start = max(0, start_idx - 100)
            context_end = min(len(transcript), start_idx + len(query) + 100)
            context = transcript[context_start:context_end]
            
            # 估算时间戳
            words_before = len(transcript[:start_idx].split())
            total_words = len(transcript.split())
            if total_words > 0:
                duration_seconds = total_words / 3
                timestamp_seconds = int((words_before / total_words) * duration_seconds)
                
                minutes = timestamp_seconds // 60
                seconds = timestamp_seconds % 60
                timestamp = f"{minutes}:{seconds:02d}"
            else:
                timestamp = "0:00"
            
            results.append({
                'video_id': vid,
                'title': title,
                'url': url,
                'context': context,
                'timestamp': timestamp,
                'timestamp_seconds': timestamp_seconds
            })
        
        return results
        
    except Exception as e:
        print(f"搜索视频时发生错误: {e}")
        return []
    finally:
        conn.close()

def generate_ai_answer(question, search_results):
    """生成AI回答"""
    if not OPENAI_API_KEY:
        print("❌ OpenAI API密钥未设置")
        return generate_fallback_answer(question, search_results)
    
    openai.api_key = OPENAI_API_KEY
    
    try:
        system_prompt = """你是一个视频问答助手，基于用户提供的视频内容回答问题。请根据提供的视频片段信息，给出专业、准确且有用的回答。在回答中，可以引用具体的视频内容和时间点。如果提供的视频片段不足以回答问题，请诚实地告知用户。"""
        
        user_message = f"用户问题: {question}\n\n"
        
        if search_results:
            user_message += "相关视频片段:\n"
            for i, result in enumerate(search_results):
                user_message += f"{i+1}. 视频标题: {result['title']}\n"
                user_message += f"   时间点: {result['timestamp']}\n"
                user_message += f"   相关内容: {result['context']}\n\n"
        else:
            user_message += "没有找到相关的视频片段。"
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"OpenAI API错误: {e}")
        return generate_fallback_answer(question, search_results)

def generate_fallback_answer(question, search_results):
    """备选回答"""
    if not search_results:
        return "抱歉，我没有在视频库中找到与您问题相关的信息。您可以尝试添加更多相关视频到视频库，或者换个问题试试。"
    
    answer = f"根据视频库中的内容，我找到了以下与\"{question}\"相关的信息：\n\n"
    
    for i, result in enumerate(search_results):
        video = get_video_by_id(result['video_id'])
        answer += f"**{i+1}. {result['title']}** (时间点: {result['timestamp']})\n"
        answer += f"相关片段: {result['context']}\n\n"
    
    answer += "您可以直接点击时间点跳转到视频的相应位置观看详细内容。"
    return answer

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_videos', methods=['GET', 'POST'])
def add_videos():
    if request.method == 'POST':
        urls = request.form.get('urls', '').strip()
        url_list = [url.strip() for url in urls.split('\n') if url.strip()]
        
        print(f"收到 {len(url_list)} 个URL")
        
        added_count = 0
        for url in url_list:
            print(f"\n处理URL: {url}")
            video_info = get_video_info(url)
            if video_info:
                success = add_video(url, video_info['title'], video_info['description'], video_info['transcript'])
                if success:
                    added_count += 1
                    print(f"✓ 成功添加: {video_info['title']}")
                    print(f"  频道: {video_info.get('channel_title', '未知')}")
                    print(f"  时长: {video_info.get('duration', '未知')}秒")
                    print(f"  观看次数: {video_info.get('view_count', '未知')}")
                else:
                    print(f"✗ 数据库错误: {url}")
            else:
                print(f"✗ 获取信息失败: {url}")
        
        return render_template('add_videos.html', message=f"成功添加 {added_count} 个视频")
    
    return render_template('add_videos.html')

@app.route('/auto_build', methods=['GET', 'POST'])
def auto_build():
    """自动构建视频库页面"""
    if request.method == 'POST':
        keywords_input = request.form.get('keywords', '').strip()
        keywords = [keyword.strip() for keyword in keywords_input.split(',') if keyword.strip()]
        
        if not keywords:
            return render_template('auto_build.html', message="请输入至少一个关键词")
        
        print(f"开始自动构建，关键词: {keywords}")
        added_count = auto_build_video_library(keywords)
        
        return render_template('auto_build.html', message=f"自动构建完成！成功添加 {added_count} 个优质视频")
    
    return render_template('auto_build.html')

@app.route('/video_list')
def video_list():
    videos = get_all_videos()
    return render_template('video_list.html', videos=videos)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        question = request.form.get('question', '')
        results = search_videos(question)
        answer = generate_ai_answer(question, results)
        
        # 修复：添加空结果判断
        video_id = results[0]['video_id'] if results else None
        timestamp = results[0]['timestamp'] if results else None
        
        # 只有在有结果时才保存对话记录
        if video_id:
            add_conversation(question, answer, video_id, timestamp)
        
        return render_template('chat.html', 
                             question=question, 
                             answer=answer, 
                             results=results)
    
    return render_template('chat.html')

if __name__ == '__main__':
    # 生产环境配置
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    
    app.run(host='0.0.0.0', port=port, debug=debug)