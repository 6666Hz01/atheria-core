import threading, pyttsx3, time
from flask import Flask, render_template_string
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# تنظیمات صدا
try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
    HAS_VOICE = True
except:
    HAS_VOICE = False

def speak(text):
    print(f"Atheria: {text}")
    socketio.emit('status', {'state': 'speaking', 'msg': text})
    if HAS_VOICE:
        try:
            engine.say(text)
            engine.run_and_wait()
        except: pass
    socketio.emit('status', {'state': 'idle', 'msg': 'آتریا آماده است'})

INTERFACE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #000; color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; font-family: sans-serif; }
        .orb { width: 150px; height: 150px; border-radius: 50%; transition: 0.5s; box-shadow: 0 0 50px #00d4ff; background: radial-gradient(circle, #00d4ff, #0055ff); }
        .speaking { box-shadow: 0 0 80px #0f0; background: radial-gradient(circle, #0f0, #050); transform: scale(1.2); }
        #log { margin-top: 30px; text-align: center; color: #00d4ff; font-size: 1.2em; padding: 0 20px; }
    </style>
</head>
<body>
    <div id="orb" class="orb"></div>
    <div id="log">در حال اتصال...</div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <script>
        var socket = io();
        socket.on('connect', function() { document.getElementById('log').innerText = 'آتریا آنلاین است'; });
        socket.on('status', function(data) {
            document.getElementById('log').innerText = data.msg;
            if(data.state === 'speaking') document.getElementById('orb').classList.add('speaking');
            else document.getElementById('orb').classList.remove('speaking');
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(INTERFACE)

def background_task():
    # در اینجا فعلاً یک حلقه ساده داریم تا سیستم زنده بماند
    while True:
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=background_task, daemon=True).start()
    print("--- Atheria Core: Online (Stable Mode) ---")
    socketio.run(app, host='0.0.0.0', port=5500)
