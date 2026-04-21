# 🚀 Tele2Rub

انتقال خودکار فایل از تلگرام به روبیکا — سریع، ساده، بدون هزینه و دردسر

**پشتیبانی از ارسال فایل تا ۲ گیگابایت**

---

## 🧠 معرفی

**Tele2Rub**

یک ابزار سبک و کاربردی است که فایل‌ها را از بات تلگرام دریافت کرده و به صورت خودکار به **سیو مسیج (Saved Messages)** روبیکا ارسال می‌کند.

کل فرایند به صورت **صف (Queue)** انجام می‌شود تا از بروز خطا و تداخل جلوگیری شود.

---

## ⚙️ نحوه کار

```text
ارسال به روبیکا → صف پردازش → دانلود فایل → ربات تلگرام
```

* دریافت فایل از تلگرام
* ذخیره موقت در سرور
* ثبت در صف
* ارسال خودکار توسط **Worker**

---

## ✨ قابلیت‌ها

* 📥 دریافت انواع فایل از تلگرام
* 📤 ارسال خودکار به روبیکا
* 🧾 ارسال همه فایل‌ها به صورت **Document**
* 📦 حفظ فرمت فایل‌های مهم (**mp4, zip, jpg و ...**)
* 🧹 ارسال سایر فایل‌ها بدون پسوند
* ⚡ سیستم صف برای جلوگیری از **کرش و تداخل**
* 🔄 اجرای جداگانه پردازش برای **پایداری بیشتر**

---

## 🛠 نصب سریع

ابتدا پروژه را دریافت کنید:

```bash
git clone https://github.com/caffeinexz/Tele2Rub.git
cd Tele2Rub
```

نصب وابستگی‌ها:

```bash
pip install -r requirements.txt
```

اجرای پروژه:

```bash
python3 main.py
```

---

## 🖥 نصب روی سرور

### 1. نصب پیش‌نیازها

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git -y
```

---

### 2. دریافت پروژه

```bash
git clone https://github.com/caffeinexz/Tele2Rub.git
cd Tele2Rub
```

---

### 3. ساخت محیط مجازی

```bash
python3 -m venv venv
```

---

### 4. فعال‌سازی محیط مجازی

```bash
source venv/bin/activate
```

---

### 5. نصب وابستگی‌ها

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 6. ساخت فایل تنظیمات

```bash
nano .env
```

و مقادیر زیر را وارد کنید:

```env
API_ID=عدد_API
API_HASH=کد_API
BOT_TOKEN=توکن_ربات
RUBIKA_SESSION=rubsession
```

---

### 7. اجرای دائمی (Screen)

```bash
screen -S tele2rub
source venv/bin/activate
python main.py
```

---

## ⚙️ تنظیمات

یک فایل `.env` در **ریشه پروژه** بسازید:

```env
API_ID=عدد_API
API_HASH=کد_API
BOT_TOKEN=توکن_ربات
RUBIKA_SESSION=rubsession
```

یا از فایل نمونه استفاده کنید:

```bash
cp .env.example .env
```

---

## 🔐 اجرای اولیه

در اولین اجرا:

* شماره روبیکا را وارد کنید
* کد تایید را وارد کنید
* فایل سشن ذخیره می‌شود و در دفعات بعد نیاز نیست

---

## 📥 نحوه استفاده

1. وارد **بات تلگرام** شوید
2. فایل ارسال کنید
3. فایل به صورت خودکار در **Saved Messages روبیکا** ارسال می‌شود

---
