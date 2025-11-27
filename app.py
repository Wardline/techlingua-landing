import os, json, threading
from pathlib import Path
from flask import Flask, render_template, jsonify

app = Flask(__name__)
COUNTER_FILE = Path("data") / "interest_counter.json"
_lock = threading.Lock()

def load_counter():
    try:
        if COUNTER_FILE.exists():
            with open(COUNTER_FILE,"r",encoding="utf-8") as f:
                return int(json.load(f).get("count",0))
    except:
        pass
    return 0

def save_counter(v):
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COUNTER_FILE,"w",encoding="utf-8") as f:
        json.dump({"count":v},f,ensure_ascii=False)

@app.route("/")
def index():
    return render_template("index.html", count=load_counter())

@app.post("/api/interest")
def api_interest():
    with _lock:
        c = load_counter()+1
        save_counter(c)
    return jsonify({"count":c})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8000,debug=True)
