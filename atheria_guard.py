import os
import shutil
import datetime
import sys
import subprocess

# --- تنظیمات هسته ---
MAIN_BOT_FILE = "atheria.py"
SAFE_ZONE = "ATHERIA_SAFE_ZONE"
LOG_FILE = "guard_history.log"

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def get_status():
    """بررسی سلامت محیط و فایل‌ها"""
    log("🔍 در حال بررسی سلامت سیستم...")
    issues = []
    
    # چک کردن وجود فایل اصلی
    if not os.path.exists(MAIN_BOT_FILE):
        issues.append(f"❌ فایل اصلی ({MAIN_BOT_FILE}) پیدا نشد!")
    
    # چک کردن فضای دیسک (در Termux مهم است)
    df = subprocess.check_output(['df', '-h', '.']).decode().split('\n')[1].split()
    usage = df[4]
    log(f"📊 میزان فضای باقی‌مانده در Termux: {usage} استفاده شده.")
    
    # چک کردن کتابخانه‌ها
    try:
        subprocess.check_output([sys.executable, "-m", "pip", "check"], stderr=subprocess.STDOUT)
        log("✅ کتابخانه‌های پایتون سالم هستند.")
    except subprocess.CalledProcessError:
        issues.append("⚠️ تداخل در کتابخانه‌های پایتون (Dependency Conflict)!")

    if not issues:
        log("✅ سیستم در وضعیت سلامت کامل قرار دارد.")
    else:
        for issue in issues:
            log(issue)
    return issues

def backup():
    """ایجاد نقطه بازگشت امن"""
    log("🛡️ در حال ایجاد نقطه بازگشت (Checkpoint)...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"snapshot_{timestamp}"
    snapshot_path = os.path.join(SAFE_ZONE, snapshot_name)

    try:
        if not os.path.exists(SAFE_ZONE):
            os.makedirs(SAFE_ZONE)
        
        # کپی کردن فایل‌های حیاتی به جای کل پروژه (برای سرعت بیشتر و حجم کمتر)
        shutil.copy2(MAIN_BOT_FILE, snapshot_path + "_" + MAIN_BOT_FILE)
        # کپی کردن فایل‌های تنظیمات و دیتابیس اگر وجود داشته باشند
        for extra in ["requirements_atheria.txt", "env_example.txt", ".env"]:
            if os.path.exists(extra):
                shutil.copy2(extra, os.path.join(snapshot_path, extra))

        with open(os.path.join(SAFE_ZONE, "latest_stable.txt"), "w") as f:
            f.write(snapshot_path)
            
        log(f"✅ بک‌آپ موفقیت‌آمیز بود: {snapshot_name}")
    except Exception as e:
        log(f"❌ خطا در بک‌آپ: {e}")

def recover():
    """بازگشت به آخرین وضعیت سالم"""
    log("🚨 عملیات بازگشت به حالت قبل (RECOVERY) شروع شد...")
    try:
        with open(os.path.join(SAFE_ZONE, "latest_stable.txt"), "r") as f:
            last_stable = f.read().strip()
        
        if os.path.exists(last_stable):
            # پیدا کردن نام فایل اصلی از روی مسیر بک‌آپ
            original_name = MAIN_BOT_FILE
            # جایگزینی فایل خراب با فایل سالم
            # نکته: در این نسخه ساده، ما فایل اصلی را از بک‌آپ جایگزین می‌کنیم
            # برای دقت بیشتر، باید نام دقیق فایل در بک‌آپ را داشته باشیم
            # از آنجایی که در backup نام را تغییر دادیم، اینجا ساده‌تر می‌کنیم:
            
            # پیدا کردن فایل در پوشه بک‌آپ (جستجوی فایل اصلی)
            found = False
            for root, dirs, files in os.walk(last_stable):
                if MAIN_BOT_FILE in files:
                    shutil.copy2(os.path.join(root, MAIN_BOT_FILE), MAIN_BOT_FILE)
                    found = True
                    break
            
            if found:
                log("✅ فایل اصلی با موفقیت از نسخه سالم بازیابی شد!")
            else:
                log("❌ فایل اصلی در بک‌آپ یافت نشد!")
        else:
            log("❌ هیچ نسخه سالمی برای بازگشت یافت نشد.")
    except Exception as e:
        log(f"❌ خطا در بازگشت: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("استفاده نادرست! دستورات: \n  python atheria_guard.py status (بررسی سلامت)\n  python atheria_guard.py backup (بک‌آپ گرفتن)\n  python atheria_guard.py recover (تعمیر اضطراری)")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "status":
        get_status()
    elif cmd == "backup":
        backup()
    elif cmd == "recover":
        recover()
    else:
        print("دستور نامعتبر!")
