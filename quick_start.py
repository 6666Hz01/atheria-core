import os
import subprocess
import sys

def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        print(f"Error running {cmd}: {e}")

def main():
    print("🚀 Starting Atheria Quick-Start Protocol...")
    
    # ۱. رفتن به پوشه اصلی
    os.chdir(os.path.expanduser("~/atheria_live"))
    print("✅ Entered directory: ~/atheria_live")

    # ۲. فعال کردن محیط مجازی (اگر وجود داشته باشد)
    env_path = os.path.expanduser("~/atheria_env/bin/activate")
    if os.path.exists(env_path):
        print("✅ Virtual Environment found. Activating...")
        # چون subprocess محیط را برای ترمینال اصلی تغییر نمی‌دهد، فقط چاپ می‌کنیم
        # کاربر باید خودش در ترمینال اصلی source بزند، اما ما اینجا آماده‌سازی می‌کنیم
    else:
        print("⚠️ Virtual Environment not found! Creating a new one...")
        run_cmd("python -m venv ~/atheria_env")

    # ۳. ساخت فایل .gitignore اگر وجود ندارد
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w") as f:
            f.write("*.db\n*.log\n__pycache__/\n.env\natheria.db\n")
        print("✅ Created .gitignore")

    print("\n" + "="*30)
    print("🎯 ALL DONE! NOW RUN THIS COMMAND TO START:")
    print("source ~/atheria_env/bin/activate && python atheria_real.py")
    print("="*30)

if __name__ == "__main__":
    main()
