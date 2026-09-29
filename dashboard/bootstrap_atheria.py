import os
import subprocess
import sys

def install_libs():
    print("[Atheria Bootstrap]: Checking dependencies...")
    libs = ["speechrecognition", "edge-tts", "flask", "flask-socketio", "flask-cors"]
    for lib in libs:
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

def create_master_file():
    print("[Atheria Bootstrap]: Creating master engine...")
    code = """
import threading, os, asyncio
from flask import Flask, SocketIO
import speech_recognition as sr
import edge_tts

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
VOICE_ID = "fa-IR-DilaraNeural"

class AtheriaBrain:
    def __init__(self, sio):
        self.sio = sio
        self.r = sr.Recognizer()

    def speak(self, text):
        print(f"[Atheria]: {text}")
        self.sio.emit('new_log', {'user': 'Atheria', 'msg': text, 'type': 'info'})
        asyncio.run(self._save_and_play(text))

    async def _save_and_play(self, text):
        comm = edge_tts.Communicate(text, VOICE_ID)
        await comm.save("response.mp3")
        os.system("termux-media-player play response.mp3")

    def run(self):
        while True:
            with sr.Microphone() as source:
                try:
                    audio = self.r.listen(source, timeout=None, phrase_time_limit=5)
                    cmd = self.r.recognize_google(audio, language="fa-IR")
                    print(f"User: {cmd}")
                    self.sio.emit('new_log', {'user': 'You', 'msg': cmd, 'type': 'user'})
                except: continue

@app.route('/')
def index():
    return "<h1>Atheria Core Running</h1><script>alert('Atheria is online');</script>"

if __name__ == "__main__":
    brain = AtheriaBrain(socketio)
    threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5000), daemon=True).start()
    brain.run()
"""
    with open("atheria_master.py", "w") as f:
        f.write(code)
    print("[Atheria Bootstrap]: Setup complete. Launching...")

if __name__ == "__main__":
    install_libs()
    create_master_file()
    os.system("python atheria_master.py")
