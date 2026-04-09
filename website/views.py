from flask import Blueprint, render_template, request, Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from bs4 import BeautifulSoup
from threading import Thread
from moviepy import *
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime
import assemblyai
import requests
import base64
import cv2
import yt_dlp
import openai
import os
import json
import webvtt
import re
from time import sleep

app = Flask(__name__)
DB_NAME = "Tutor"
DB_USER = "root"
DB_HOST = "localhost"
DB_Password = ""

# app.config["SQLALCHEMY_DATABASE_URI"] = f"mysql+pymysql://{DB_USER}:{DB_Password}@{DB_HOST}/{DB_NAME}"
# app.config["SQLALCHEMY_TRACK_MODIFICATION"] = False
engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_Password}@{DB_HOST}/{DB_NAME}")
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()
time = datetime.now().strftime("%m%d%Y_%H%M%S")
views = Blueprint("views", __name__)

class Video(Base):
    __tablename__ = 'video'
    __table_args__ = {'extend_existing': True} # Allows re-declaration of the table

    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)
    author = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    title_id = Column(Text, nullable=False, unique=True) # Assuming title_id is unique for file naming
    view = Column(Integer, default=0) # Maps to 'view' in your DB (renamed from 'views' for consistency with your schema)
    date = Column(DateTime, default=datetime.utcnow) # Maps to 'date' in your DB

    def __repr__(self):
        return f'<Video {self.title}>'

    # Method to serialize the video object for JSON response or template rendering
    def to_dict(self):
        views_str = str(self.view) # Use self.view
        if self.view >= 1_000_000:
            views_str = f"{self.view / 1_000_000:.1f}M"
        elif self.view >= 1_000:
            views_str = f"{self.view / 1_000:.1f}K"

        date_str = "N/A"
        if isinstance(self.date, datetime): # Use self.date
            time_diff = datetime.now() - self.date
            if time_diff.days > 365:
                date_str = f"{time_diff.days // 365} year{'s' if time_diff.days // 365 > 1 else ''} ago"
            elif time_diff.days > 30:
                date_str = f"{time_diff.days // 30} month{'s' if time_diff.days // 30 > 1 else ''} ago"
            elif time_diff.days > 7:
                date_str = f"{time_diff.days // 7} week{'s' if time_diff.days // 7 > 1 else ''} ago"
            elif time_diff.days > 0:
                date_str = f"{time_diff.days} day{'s' if time_diff.days > 1 else ''} ago"
            elif time_diff.seconds > 3600:
                date_str = f"{time_diff.seconds // 3600} hour{'s' if time_diff.seconds // 3600 > 1 else ''} ago"
            elif time_diff.seconds > 60:
                date_str = f"{time_diff.seconds // 60} minute{'s' if time_diff.seconds // 60 > 1 else ''} ago"
            else:
                date_str = "just now"
        else:
            date_str = str(self.date) # Fallback if not a datetime object

        return {
            "id": self.id,
            "title": self.title,
            "title_id": self.title_id,
            "description": self.description,
            "channel_name": self.author,
            "views": views_str,
            "upload_date": date_str,
            "video_url": f"/watch/{self.id}"
        }

@views.route('/')
def home():
    return render_template("home.html")

@views.route('/add')
def add():
    return render_template("add.html")

def parse_scholarship_detail(soup: BeautifulSoup) -> dict:
    def get_text_after_heading(heading_text):
        heading = soup.find(lambda tag: tag.name == "h2" and heading_text in tag.text)
        if not heading:
            return None
        next_tag = heading.find_next_sibling()
        if not next_tag:
            return None
        if next_tag.name == "p":
            return next_tag.get_text(strip=True)
        elif next_tag.name in ["ol", "ul"]:
            return [li.get_text(strip=True) for li in next_tag.find_all("li")]
        return None

    data = {}
    data["ทุนการศึกษา"] = get_text_after_heading("ชื่อทุนการศึกษา")
    data["หน่วยงานให้ทุน"] = get_text_after_heading("หน่วยงานให้ทุนการศึกษา")
    data["คำอธิบาย"] = get_text_after_heading("คำอธิบาย")
    data["คุณสมบัติผู้รับทุน"] = get_text_after_heading("คุณสมบัติผู้รับทุน")
    data["การสนับสนุนด้านทุนการศึกษา"] = get_text_after_heading("การสนับสนุนด้านทุนการศึกษา")
    data["ขั้นตอนการขอรับทุน"] = get_text_after_heading("ขั้นตอนการขอรับทุน")
    data["วันเปิดรับสมัคร"] = get_text_after_heading("วันเปิดรับสมัคร")

    # ดึงข้อมูลติดต่อแหล่งทุน (ลิงก์, เบอร์โทร ฯลฯ)
    contact_heading = soup.find(lambda tag: tag.name == "h2" and "ติดต่อแหล่งทุน" in tag.text)
    contact_info = []
    if contact_heading:
        next_tag = contact_heading.find_next_sibling()
        while next_tag and next_tag.name in ["p", "a", "h2"]:
            # ดึงลิงก์
            if next_tag.name == "a":
                href = next_tag.get("href")
                if href:
                    contact_info.append(href)
            # ดึงลิงก์ใน p
            elif next_tag.name == "p":
                links = next_tag.find_all("a")
                for a in links:
                    href = a.get("href")
                    if href:
                        contact_info.append(href)
                # ดึงข้อความใน p (เช่นเบอร์โทร)
                text = next_tag.get_text(strip=True)
                if text:
                    contact_info.append(text)
            next_tag = next_tag.find_next_sibling()
    data["ติดต่อแหล่งทุน"] = contact_info if contact_info else None

    return data

def scrape_scholarship_data():
    options = Options()
    options.add_argument('--headless')  # รัน Chrome แบบไม่แสดงหน้าต่าง
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    # สร้าง instance ของ Chrome WebDriver
    driver = webdriver.Chrome(options=options)

    try:
        # เปิดหน้าเว็บ list ทุน
        url = 'https://findstudentship.eef.or.th/scholarship?grade=ทุกระดับ&cost=ทุนทั้งหมด&genre=ทุนให้เปล่า'
        driver.get(url)
        sleep(3)
        Datas = []

        while True:
            link_elements = driver.find_elements(By.XPATH, "//div[contains(text(),'ไปยังแหล่งทุน')]")
            total = len(link_elements)

            for i in range(len(Datas), total):
                try:
                    link_elements = driver.find_elements(By.XPATH, "//div[contains(text(),'ไปยังแหล่งทุน')]")
                    driver.execute_script("arguments[0].click();", link_elements[i])
                    sleep(5)

                    # ดึงหน้า detail แล้วเก็บ <h1>
                    detail_html = driver.page_source
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                    data = parse_scholarship_detail(detail_soup)

                    Datas.append(data)

                    driver.back()  # กลับไปยังหน้า list
                    sleep(3)

                except IndexError:
                    break  # ออกจากลูปในกรณีองค์ประกอบหาย
            else:
                break  # ถ้าลูปทำจบครบทุกตัวโดยไม่ break → ออกลูป while

        with open("/Think-Forge/website/static/scholarship_detail.json", 'w', encoding='utf-8') as f:
            json.dump(Datas, f, ensure_ascii=False, indent=4)

    finally:
        driver.quit()

@views.route("/advice")
def advice():
    # Start the scraping in a new thread
    thread = Thread(target=scrape_scholarship_data)
    thread.start()
    
    return render_template("advice.html")

@views.route('/courses')
def courses():
    videos = [video.to_dict() for video in session.query(Video).order_by(Video.date.desc()).all()]
    return render_template('course.html', videos=videos)

@views.route('/watch/<int:video_id>/game')
def game(video_id):
    # You can fetch video details here if needed for the game page
    video = session.query(Video).get(video_id)
    if not video:
        return "Video not found for game", 404

    # Render your game template, passing necessary data
    return render_template('game.html', video_id=video_id, video_title=video.title, title_id=video.title_id)

@views.route('/watch/<int:video_id>') # <--- CHANGE THIS LINE
def watch(video_id):
    # Retrieve the video object from the database using the provided video_id
    video = session.query(Video).get(video_id) # Access the database session

    # If no video is found with that ID, return a 404 error
    if not video:
        return "Video not found", 404

    # Format data for the template (as done in previous versions of the code)
    # This logic ensures views are formatted (e.g., '1.2M views') and date is relative ('2 days ago')
    views_str = str(video.view)
    if video.view >= 1_000_000:
        views_str = f"{video.view / 1_000_000:.1f}M"
    elif video.view >= 1_000:
        views_str = f"{video.view / 1_000:.1f}K"
    else:
        views_str = str(video.view)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    summary_file_path = os.path.join(base_dir, "static", "Summaries", f"{video.title_id}_summary_text.json")

    video_summary_content = "Summary not available."

    if os.path.exists(summary_file_path):
        try:
            with open(summary_file_path, 'r', encoding='utf-8') as f:
                summary_data_list = json.load(f) # This is your list of dictionaries

                combined_summary_parts = []
                for section in summary_data_list:
                    # You want 'title', 'explanation', and 'examples' from each dictionary
                    title = section.get('title', 'N/A')
                    explanation = section.get('explanation', 'N/A')
                    examples = section.get('examples', 'N/A')

                    # Format each section as a string with newlines
                    # You can adjust this formatting as you like
                    formatted_section = (
                        f"**{title}**\n"
                        f"{explanation}\n"
                        f"Examples: {examples}\n\n" # Two newlines to separate sections
                    )
                    combined_summary_parts.append(formatted_section)

                # Join all formatted sections into a single string
                video_summary_content = "".join(combined_summary_parts).strip()

        except json.JSONDecodeError:
            video_summary_content = "Error reading summary file: Invalid JSON format."
        except Exception as e:
            video_summary_content = f"An unexpected error occurred while processing summary: {e}"
    else:
        video_summary_content = "Summary file not found for this video."

    date_str = "N/A"
    if isinstance(video.date, datetime):
        time_diff = datetime.now() - video.date
        if time_diff.days > 365:
            date_str = f"{time_diff.days // 365} year{'s' if time_diff.days // 365 > 1 else ''} ago"
        elif time_diff.days > 30:
            date_str = f"{time_diff.days // 30} month{'s' if time_diff.days // 30 > 1 else ''} ago"
        elif time_diff.days > 7:
            date_str = f"{time_diff.days // 7} week{'s' if time_diff.days // 7 > 1 else ''} ago"
        elif time_diff.days > 0:
            date_str = f"{time_diff.days} day{'s' if time_diff.days > 1 else ''} ago"
        elif time_diff.seconds > 3600:
            date_str = f"{time_diff.seconds // 3600} hour{'s' if time_diff.seconds // 3600 > 1 else ''} ago"
        elif time_diff.seconds > 60:
            date_str = f"{time_diff.seconds // 60} minute{'s' if time_diff.seconds // 60 > 1 else ''} ago"
        else:
            date_str = "just now"
    else:
        date_str = str(video.date)


    return render_template(
        "watchvdo.html",
        id=video_id,
        video_title=video.title,
        channel_name=video.author,
        description=video.description,
        views=views_str,
        upload_date=date_str,
        video_title_id=video.title_id,
        summary=video_summary_content
    )


def url_validator(url):
    try:
        result = urlparse(url)
        components = [result.scheme, result.path]
        if result.netloc != "":
            components.append(result.netloc)
        return all(components)
    except:
        return False

def download_file_vdo(file, loc):
    file.save(loc)

def FindSound(path):
    try:
        # Ensure Ignore/ directory exists
        os.makedirs("Ignore", exist_ok=True)

        # Clip first 60 seconds
        video = VideoFileClip(path).subclip(0, 60)

        audio_path = "Ignore/result.ogg"
        video.audio.write_audiofile(audio_path, logger=None)

        # Transcribe using AssemblyAI
        transcript = assemblyai.Transcriber(config=config).transcribe(audio_path)

        # Clean up audio file
        if os.path.exists(audio_path):
            os.remove(audio_path)

        # Check if text was found
        if not transcript.text.strip():
            return False
        return True

    except Exception as e:
        print(f"[FindSound] Error: {e}")
        return False

def json_convert(raw_text):
    try:
        json_data = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            cleaned = raw_text.replace("'", '"')
            cleaned = re.sub(r'\\\(|\\\)', '', cleaned)
            cleaned = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', cleaned)
            cleaned = ''.join(ch for ch in cleaned if ch.isprintable())
            json_data = json.loads(cleaned)
        except Exception as e:
            print("Failed")
            print("Error:", e)
            print("Raw content:\n", raw_text)
            exit()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(base_dir, "static", "Summaries")
    os.makedirs(upload_dir, exist_ok=True)

    with open(f"{upload_dir}/Video_{time}_summary_text.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

def generate_quizzes(language):
    base = os.path.dirname(os.path.abspath(__file__))
    upload = os.path.join(base, "static", "Summaries")
    os.makedirs(upload, exist_ok=True)
    json_result = f"{upload}/Video_{time}_summary_text.json"

    with open(json_result, mode='r', encoding="utf-8") as f:
        summary_data = json.load(f)

        pl = {
            "language":language,
            "texts":summary_data
        }

        quiz = openai.ChatCompletion.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a highly skilled educational AI tutor. Based on the provided content, your job is to generate 10 quiz questions.\n"
                        "Requirements:\n"
                        "- multiple-choice.\n"
                        f"- All questions and answers should be in {language}.\n"
                        "- Provide variety across different sections of the content.\n"
                        "- Format as a JSON array, where each item is one of:\n"
                        "{\n"
                        "  \"type\": \"multiple_choice\",\n"
                        "  \"question\": \"...\",\n"
                        "  \"choices\": [\"...\", \"...\", \"...\", \"...\"],\n"
                        "  \"answer\": \"...\"\n"
                        "}\n"
                        "OR\n"
                        "{\n"
                        "  \"type\": \"open_ended\",\n"
                        "  \"question\": \"...\",\n"
                        "  \"reference_answer\": \"...\"\n"
                        "}"
                    )
                },
                {
                    "role": "user",
                    "content": f"This is the content to base the quiz on:\n\n{json.dumps(summary_data, ensure_ascii=False)}"
                }
            ],
            temperature=0.7,
            max_tokens=2500
        )

    quiz_raw = quiz.choices[0].message.content

    try:
        quiz_json = json.loads(quiz_raw)
    except json.JSONDecodeError:
        quiz_raw_fixed = quiz_raw.replace("'", '"')
        quiz_json = json.loads(quiz_raw_fixed)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(base_dir, "static", "Quizzes")
    os.makedirs(upload_dir, exist_ok=True)

    with open(f"{upload_dir}/Video_{time}_quizzes.json", "w", encoding="utf-8") as f:
        json.dump(quiz_json, f, ensure_ascii=False, indent=2)

def Analyzer_mp4(path, prompt, language):
    with app.app_context():
        result = FindSound(path)
        if result:
            video = VideoFileClip(path)
            video.audio.write_audiofile("Ignore/summary.ogg")

            with open("Ignore/summary.ogg", mode='rb') as audio_file:
                response = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio_file
                )

            txt = response.get("text","")
            chat = openai.ChatCompletion.create(
                model="gpt-4.1-mini",
                messages=[
                    prompt,
                    {"role": "user", "content": f"This is the transcript:\n\n{txt}"}
                ],
                temperature=0.5,
                max_tokens=2500
            )

            os.remove("Ignore/summary.ogg")

            raw_text = chat["choices"][0]["message"]["content"]

            json_convert(raw_text)
        else:
            vdo = cv2.VideoCapture(path)

            base64Frames = []
            while vdo.isOpened():
                success, frame = vdo.read()
                if not success:
                    break
                _, buffer = cv2.imencode(".jpg", frame)
                base64Frames.append(base64.b64encode(buffer).decode("utf-8"))

            vdo.release()

            response = openai.ChatCompletion.create(
                model="gpt-4.1-mini",
                messages=[
                    prompt,
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "this is pictures of certain video, please summary in each section, base on the description provided."
                            },
                            *[
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{frame}"
                                    }
                                }
                                for frame in base64Frames[0::25]
                            ]
                        ]
                    }
                ],
                max_tokens=5000
            )

            raw_text = response.choices[0].message.content


            json_convert(raw_text)

        responding = requests.post("http://localhost:5678/webhook/fa2bfccb-95e1-4d40-8d09-d5ea7252d014",json={"language":language,"texts":raw_text})

        output = (responding.text).replace("`","").replace("json","")

        try:
            quiz_json = json.loads(output)
        except json.JSONDecodeError:
            output_fixed = output.replace("'", '"')
            quiz_json = json.loads(output_fixed)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        upload_dir = os.path.join(base_dir, "static", "Quizzes")
        os.makedirs(upload_dir, exist_ok=True)

        with open(f"{upload_dir}/Video_{time}_quizzes.json", "w", encoding="utf-8") as f:
            json.dump(quiz_json, f, ensure_ascii=False, indent=2)

        # generate_quizzes(language)

def generate_thumbnail_from_video(video_path, thumbnail_path, frame_time_sec=1):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_time_sec * fps)

    ret, frame = cap.read()
    if ret:
        cv2.imwrite(thumbnail_path, frame)

    cap.release()

@views.route("/", methods=["POST","GET"])
def pending():
    vdo = request.files.get("videoFile")
    language_selected = request.form.get("language")
    title = request.form.get("videoTitle")
    vdoauthor = request.form.get("authorName")
    description = request.form.get("videoDescription")
    thumbnail_file = request.files.get('thumbnailFile') # Get the thumbnail file from request.files

    openai.api_key = "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"
    assemblyai.settings.api_key = os.getenv("ASSEMBLY_API_KEY")

    summary_prompt = {
        "role": "system", "content": (
            "You are a genius tutor generating structured lesson summaries from transcripts. "
            "The following is a transcript from a math video. Your task is to:\n"
            f"1. use {language_selected} as the main language in this summary."
            "2. Divide the content into logical sections or 'chapters' based on topic changes.\n"
            "3. For each section, provide:\n"
            "   - A clear title (`title`)\n"
            "   - A detailed explanation (`explanation`)\n"
            "   - Any relevant formulas or examples that appear (`examples`)\n"
            "4. Return the result as a JSON array like this:\n"
            "[{'title': 'หัวข้อย่อย 1', 'explanation': 'อธิบายเนื้อหาโดยละเอียดที่เกี่ยวกับหัวข้อนั้น', 'examples': 'ตัวอย่างและสูตรที่มีในช่วงนั้น'}, ...]"
        )
    }

    config = assemblyai.TranscriptionConfig(speech_model=assemblyai.SpeechModel.nano)

    if vdo and vdo.mimetype == "video/mp4":
        base_dir = os.path.dirname(os.path.abspath(__file__))
        video_upload_dir = os.path.join(base_dir, "static", "VideoDump")
        thumbnail_upload_dir = os.path.join(base_dir, "static", "Thumbnails") # New directory for thumbnails
        os.makedirs(video_upload_dir, exist_ok=True)
        os.makedirs(thumbnail_upload_dir, exist_ok=True) # Create thumbnail directory

        video_filename = f"Video_{time}.mp4"
        save_video_path = os.path.join(video_upload_dir, video_filename)
        vdo.save(save_video_path)

        thumbnail_filename = f"Thumbnail_Video_{time}.png" # Default thumbnail filename
        save_thumbnail_path = os.path.join(thumbnail_upload_dir, thumbnail_filename)

        if thumbnail_file and thumbnail_file.filename != '': # Check if a thumbnail file was actually uploaded
            if thumbnail_file.mimetype.startswith('image/'):
                thumbnail_file.save(save_thumbnail_path)
            else:
                generate_thumbnail_from_video(save_video_path, save_thumbnail_path)
        else:
            # No thumbnail provided, generate one from the video
            generate_thumbnail_from_video(save_video_path, save_thumbnail_path)


        Thread(target=Analyzer_mp4, args=(save_video_path, summary_prompt, language_selected)).start()

        new_video = Video(
            title=title,
            author=vdoauthor,
            title_id=f"Video_{time}",
            description=description
        )
        session.add(new_video)
        session.commit()
        session.close()

        return render_template('add.html')
    else:
        return render_template("add.html",error=f"The provided file is not in MP4 format.")