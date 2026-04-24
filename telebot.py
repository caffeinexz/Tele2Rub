import os
import re
import json
from pathlib import Path
from typing import Optional
import random
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import yt_dlp


load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
QUEUE_DIR = BASE_DIR / "queue"
QUEUE_FILE = QUEUE_DIR / "tasks.jsonl"
#cache for saving url to download
CHACHE = QUEUE_DIR / "cache.json"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)

with open(CHACHE, "w") as f:
    f.write("{}")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise RuntimeError("Please set API_ID, API_HASH and BOT_TOKEN in .env")

app = Client(
    "tel2rub",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file.bin").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name[:200] or "file.bin"


def split_name(filename: str) -> tuple[str, str]:
    path = Path(filename)
    return path.stem, path.suffix


def get_media(message: Message):
    media_types = [
        ("document", message.document),
        ("video", message.video),
        ("audio", message.audio),
        ("voice", message.voice),
        ("photo", message.photo),
        ("animation", message.animation),
        ("video_note", message.video_note),
        ("sticker", message.sticker),
    ]

    for media_type, media in media_types:
        if media:
            return media_type, media

    return None, None


def build_download_filename(message: Message, media_type: str, media) -> str:
    original_name = getattr(media, "file_name", None)

    if not original_name:
        file_unique_id = getattr(media, "file_unique_id", None) or "file"

        default_extensions = {
            "document": ".bin",
            "video": ".mp4",
            "audio": ".mp3",
            "voice": ".ogg",
            "photo": ".jpg",
            "animation": ".mp4",
            "video_note": ".mp4",
            "sticker": ".webp",
        }

        original_name = f"{file_unique_id}{default_extensions.get(media_type, '.bin')}"

    original_name = safe_filename(original_name)
    stem, suffix = split_name(original_name)

    unique_name = f"{stem}_{message.id}{suffix or '.bin'}"
    return safe_filename(unique_name)


def append_task(task: dict) -> None:
    with open(QUEUE_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(task, ensure_ascii=False) + "\n")


#progress message in downloading
async def prog(c,total,t,client,user_id):                                   
    #this function show the progress of downlaoing
    #to prevent error of fast editing i made random system to update the progres                                                                            
    try:                                                                    
        alf = random.randint(1,100)                                         
        # print(alf)                                                      
        if alf==50:                                                         
                                                                            
            await client.edit_message_text(                                 
            chat_id=t.chat.id,                                                          
            message_id=t.id,
            text=f"در حال دانلود {(c*100)/total:.1f}%"
        )
    except Exception as e:
        print(e)
        pass
    


@app.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):

    start_message = """فایل رو بفرست
    برای دانلود از لینک از دستور /link <url> استفاده کن."""
    await message.reply_text(start_message)


@app.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
        | filters.voice
        | filters.photo
        | filters.animation
        | filters.video_note
        | filters.sticker
    )
)
async def media_handler(client: Client, message: Message):
    media_type, media = get_media(message)
    if not media:
        await message.reply_text("فایل قابل پردازش نیست.")
        return

    download_name = build_download_filename(message, media_type, media)
    download_path = DOWNLOAD_DIR / download_name

    status = await message.reply_text("فایل رفت توی صف پردازش.")
    
    try:
        downloaded = await client.download_media(
            message,
            file_name=str(download_path),
            progress=prog,progress_args= (status,client,message.from_user.id)
        )

        if not downloaded:
            raise RuntimeError("Download failed.")

        await status.edit_text("فایل از تلگرام با موفقیت دانلود شد.")
        downloaded_path = Path(downloaded)
        if not downloaded_path.exists():
            raise RuntimeError("Downloaded file not found.")

        task = {
            "type": "local_file",
            "path": str(downloaded_path),
            "caption": message.caption or "",
            "chat_id": message.chat.id,
            "status_message_id": status.id,
        }

        append_task(task)

    except Exception as e:
        await status.edit_text(f"خطا: {str(e)}")



#########################################################################
#download link section  
def add_cache(id,url):

    with open(CHACHE,"r",encoding="UTF-8") as f:
        data = json.load(f)
    
    data[id] = url
    with open(CHACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data

def read_cache():

    with open(CHACHE,"r",encoding="UTF-8") as f:
        data = json.load(f)

    return data


def get_formats(url):
    ydl_opts = {"quiet": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = []
    for f in info["formats"]:
        if f.get("ext") and f.get("format_id"):
            formats.append({
                "id": f["format_id"],
                "ext": f["ext"],
                "res": f.get("format_note") or f.get("height") or f.get("format") or f.get("resolution"),
                "url":f.get("url")
            })
    return formats


@app.on_message(filters.command("link"))
async def link_handler(client, message):
    url = message.command[1].strip()

    try:
        formats = get_formats(url)
    except:
        await message.reply("Failed to read video.")
        return
    
    add_cache(message.id,url)

    buttons = []
    urls = "لینک‌ها به‌ترتیب همراه با دکمه‌ها قرار داده شده‌اند:\n"
    for f in formats:
        urls += f["url"]+"\n"
        label = f'{f["res"]}--{f["ext"]}'
        data = f"{message.id}|{f['id']}|{f['ext']}"
        buttons.append([InlineKeyboardButton(label, callback_data=data)])

    await message.reply(urls)
    await message.reply(
        "Select format:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query()
async def callback_handler(client, callback_query):
    msg_id, format_id,ext = callback_query.data.split("|")
    url_cache = read_cache()

    url = url_cache.get(msg_id)

    if not url:
        await callback_query.answer("Expired.")
        return


    filename = f"download_{msg_id}_{format_id}.{ext}"
    ydl_opts = {
        "format": format_id,
        "outtmpl": filename
    }
    await callback_query.message.edit_text("در حال دانلود...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)

    await callback_query.message.edit_text("درحال ارسال...")
    
    await client.send_document(
        chat_id=callback_query.message.chat.id,
        document=file_path,
        caption=filename,
        reply_to_message_id=callback_query.message.id
    )
    

    os.remove(filename)


if __name__ == "__main__":
    app.run()
