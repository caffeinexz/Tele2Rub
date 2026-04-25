import os
import re
import json
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rubpy import Client as RubikaClient
import requests
import pyzipper
from urllib.parse import urlparse
import threading

load_dotenv()

SESSION = os.getenv("RUBIKA_SESSION", "rubika_session").strip()

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
QUEUE_DIR = BASE_DIR / "queue"
QUEUE_FILE = QUEUE_DIR / "tasks.jsonl"
PROCESSING_FILE = QUEUE_DIR / "processing.json"
FAILED_FILE = QUEUE_DIR / "failed.jsonl"
STATUS_FILE = QUEUE_DIR / "status.jsonl"
URL_DIR = DOWNLOAD_DIR / "url"
CANCEL_FILE = QUEUE_DIR / "cancelled.jsonl"

MAX_RETRIES = 5
UPLOAD_TIMEOUT = 600
TARGET = "me"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
URL_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name[:200] or "file"

def pretty_size(size) -> str:
    size = float(size or 0)
    units = ["B", "KB", "MB", "GB"]

    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"

def eta_text(seconds) -> str:
    if not seconds or seconds <= 0:
        return "نامشخص"

    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def push_status(task: dict, text: str, status: str = "working", percent: float | None = None):
    payload = {
        "chat_id": task.get("chat_id"),
        "message_id": task.get("status_message_id"),
        "status": status,
        "text": text,
        "percent": percent,
        "time": time.time(),
    }

    with open(STATUS_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

def is_cancelled(task: dict) -> bool:
    job_id = str(task.get("job_id", ""))

    if not job_id or not CANCEL_FILE.exists():
        return False

    with open(CANCEL_FILE, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            item = json.loads(line)
            if str(item.get("job_id")) == job_id:
                return True

    return False

def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 1

    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def has_session(session_name: str) -> bool:
    candidates = [
        Path(session_name),
        Path(f"{session_name}.session"),
        Path(f"{session_name}.sqlite"),
    ]
    return any(path.exists() for path in candidates)


def ensure_session():
    if has_session(SESSION):
        return

    client = RubikaClient(name=SESSION)

    try:
        client.start()
        print("Login successful.")
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def send_document(file_path: str, caption: str = ""):
    client = RubikaClient(name=SESSION)

    try:
        client.start()
        return client.send_document(
            TARGET,
            file_path,
            caption=caption or ""
        )
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

def send_with_timeout(file_path, caption, timeout):
    result = {}
    error = {}

    def target():
        try:
            result["data"] = send_document(file_path, caption)
        except Exception as e:
            error["err"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise RuntimeError("آپلود بیشتر از حد مجاز طول کشید و لغو شد.")

    if "err" in error:
        raise error["err"]

    return result.get("data")

def send_with_retry(file_path: str, caption: str = "", task: dict | None = None):
    last_error = None
    start_time = time.time()

    for attempt in range(1, MAX_RETRIES + 1):

        if time.time() - start_time > UPLOAD_TIMEOUT:
            raise RuntimeError("آپلود بیشتر از حد مجاز طول کشید و لغو شد.")

        if task and is_cancelled(task):
            raise RuntimeError("ارسال لغو شد.")

        try:
            if task:
                push_status(
                    task,
                    f"🔼 در حال آپلود در روبیکا...\n\n"
                    f"🔴 تلاش {attempt} از {MAX_RETRIES}\n\n"
                    f"برای لغو ارسال:\n"
                    f"`/del {task.get('job_id')}`",
                    "uploading"
                )

            return send_with_timeout(file_path, caption, 60)

        except Exception as e:
            last_error = e
            error_text = str(e).lower()

            transient = any(
                key in error_text
                for key in [
                    "502", "503", "bad gateway", "timeout",
                    "cannot connect", "connection reset",
                    "temporarily unavailable",
                    "error uploading chunk",
                    "unexpected mimetype",
                ]
            )

            if transient and attempt < MAX_RETRIES:

                if task and is_cancelled(task):
                    raise RuntimeError("ارسال لغو شد.")

                if task:
                    push_status(
                        task,
                        f"ارتباط با روبیکا ناپایدار بود...\n"
                        f"دوباره تلاش می‌کنم ({attempt + 1})",
                        "uploading"
                    )

                time.sleep(3)
                continue

    raise last_error if last_error else RuntimeError("Upload failed.")

def download_url(task: dict) -> Path:
    url = task.get("url", "").strip()
    if not url:
        raise RuntimeError("URL خالیه")

    push_status(task, "در حال دانلود ...", "downloading", 0)

    try:
        resp = requests.get(url, stream=True, timeout=(10, 60), allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("لینک جواب نداد")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("مشکل شبکه")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "نامشخص"
        raise RuntimeError(f"دانلود انجام نشد. کد خطا: {code}")
    
    cd = resp.headers.get("content-disposition", "")
    match = re.findall(r'filename="(.+?)"', cd)
    name = match[0] if match else Path(urlparse(url).path).name
    name = safe_filename(name or f"file_{int(time.time())}")
    if "." not in name:
        name += ".bin"

    target = unique_path(URL_DIR / name)
    total = int(resp.headers.get("content-length") or 0)
    downloaded, last_update, started = 0, 0, time.time()

    with open(target, "wb") as f:
        for chunk in resp.iter_content(1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_update < 3 and downloaded < total:
                continue
            last_update = now

            speed = downloaded / max(now - started, 1)
            eta = (total - downloaded) / speed if total and speed else None
            percent = downloaded * 100 / total if total else None

            text = f"داره دانلود میکنه...\n\n{pretty_size(downloaded)}"
            if total:
                text += f" از {pretty_size(total)}"
            text += f"\nسرعت: {pretty_size(speed)}/s"
            if eta:
                text += f"\nمونده: {eta_text(eta)}"

            push_status(task, text, "downloading", percent)

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("فایل دانلود نشد")

    task["file_name"] = target.name
    task["file_size"] = target.stat().st_size
    return target

def make_zip_with_password(file_path: Path, password: str) -> Path:
    zip_path = unique_path(file_path.with_suffix(file_path.suffix + ".zip"))

    with pyzipper.AESZipFile(
        zip_path,
        "w",
        compression=pyzipper.ZIP_STORED,
        encryption=pyzipper.WZ_AES,
    ) as zip_file:
        zip_file.setpassword(password.encode("utf-8"))
        zip_file.write(file_path, arcname=file_path.name)

    return zip_path

def pop_first_task():
    if not QUEUE_FILE.exists():
        return None

    with open(QUEUE_FILE, "r", encoding="utf-8") as file:
        lines = [line for line in file if line.strip()]

    if not lines:
        return None

    first_line = lines[0]
    remaining = lines[1:]

    with open(QUEUE_FILE, "w", encoding="utf-8") as file:
        file.writelines(remaining)

    return json.loads(first_line)


def save_processing(task: dict) -> None:
    with open(PROCESSING_FILE, "w", encoding="utf-8") as file:
        json.dump(task, file, ensure_ascii=False, indent=2)


def clear_processing() -> None:
    if PROCESSING_FILE.exists():
        PROCESSING_FILE.unlink()


def append_failed(task: dict, error: str) -> None:
    payload = {"task": task, "error": error}
    with open(FAILED_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

def process_task(task: dict):
    task_type = task.get("type")
    caption = task.get("caption", "")
    safe_mode = task.get("safe_mode", False)
    zip_password = task.get("zip_password", "")

    local_path: Path | None = None

    if task_type == "local_file":
        local_path = Path(task.get("path", ""))

        if not local_path.exists():
            raise RuntimeError("Local file not found.")

    elif task_type == "direct_url":
        local_path = download_url(task)

    else:
        raise RuntimeError("Unknown task type.")

    if safe_mode and zip_password:
        push_status(task, "در حال تبدیل به فایل zip ...", "processing")

        try:
            zipped = make_zip_with_password(local_path, zip_password)
        finally:
            try:
                if local_path.exists():
                    local_path.unlink()
            except Exception:
                pass

        send_path = zipped

    else:
        send_path = local_path

    try:
        if is_cancelled(task):
            raise RuntimeError("ارسال لغو شد.")

        send_with_retry(str(send_path), caption, task)

        push_status(
            task,
            "فایل با موفقیت در روبیکا آپلود شد.",
            "done"
        )

    finally:
        try:
            if send_path and send_path.exists():
                send_path.unlink()
        except Exception:
            pass

def worker_loop():
    ensure_session()
    print("Rubika worker started.")

    while True:
        task = pop_first_task()

        if not task:
            time.sleep(0.2)
            continue

        save_processing(task)

        try:
            process_task(task)
        except Exception as e:
            append_failed(task, str(e))
            push_status(task, f"خطا: {str(e)}", "failed")
        finally:
            clear_processing()

if __name__ == "__main__":
    worker_loop()
