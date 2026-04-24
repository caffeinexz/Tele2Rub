import os
import re
import json
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rubpy import Client as RubikaClient


load_dotenv()

SESSION = os.getenv("RUBIKA_SESSION", "rubika_session").strip()

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
QUEUE_DIR = BASE_DIR / "queue"
QUEUE_FILE = QUEUE_DIR / "tasks.jsonl"
PROCESSING_FILE = QUEUE_DIR / "processing.json"
FAILED_FILE = QUEUE_DIR / "failed.jsonl"

MAX_RETRIES = 5
RETRY_DELAY = 3
TARGET = "me"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)


KEEP_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".pdf", ".txt", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name[:200] or "file"


def remove_extension(name: str) -> str:
    name = safe_filename(name)
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name or "file"


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




def send_with_retry(file_path: str, caption: str = ""):
    last_error = None
    client = RubikaClient(name=SESSION)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client.start()
            tx = f"""در حال ارسال فایل
                    {file_path}
                    """
            client.send_message(TARGET,tx)
            client.send_document(
                TARGET,
                file_path,
                caption=caption or ""
            )

            return
        except Exception as e:
            last_error = e
            error_text = str(e).lower()

            transient = any(
                key in error_text
                for key in [
                    "502",
                    "bad gateway",
                    "timeout",
                    "cannot connect",
                    "connection reset",
                    "temporarily unavailable",
                    "error uploading chunk",
                ]
            )


            error_msg = f"""Attempt {attempt}/{MAX_RETRIES} failed \nerror: {error_text} """
            client.send_message(TARGET,error_msg)
            if transient and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue

            break

            

        finally:
            try:
                os.remove(file_path)
                client.disconnect()
            except Exception:
                pass
    raise last_error if last_error else RuntimeError("Upload failed.")


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


def should_keep_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in KEEP_EXTENSIONS


def process_task(task: dict):
    task_type = task.get("type")
    caption = task.get("caption", "")

    if task_type != "local_file":
        raise RuntimeError("Unknown task type.")

    original_path = Path(task.get("path", ""))
    if not original_path.exists():
        raise RuntimeError("Local file not found.")

    if should_keep_extension(original_path.name):
        send_path = original_path
    else:
        clean_name = remove_extension(original_path.name)
        send_path = unique_path(original_path.parent / clean_name)

        try:
            original_path.rename(send_path)
        except Exception:
            send_path = original_path

    try:
        send_with_retry(str(send_path), caption)
    finally:
        try:
            if send_path.exists():
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
            client = RubikaClient(name=SESSION)
            client.start()
            client.send_message(TARGET,f"{task}\n{str(e)}")
            append_failed(task, str(e))
            client.disconnect()
        finally:
            clear_processing()


if __name__ == "__main__":
    worker_loop()
