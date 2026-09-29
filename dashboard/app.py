
from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    # خواندن لاگ‌های سیستم برای نمایش در داشبورد
    logs = []
    if os.path.exists("logs/system.log"):
        with open("logs/system.log", "r", encoding="utf-8") as f:
            logs = f.readlines()[-10:] # ۱۰ خط آخر لاگ
    return render_template("index.html", logs=logs)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
