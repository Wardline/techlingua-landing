import json
import threading
from pathlib import Path
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# файл со счётчиком кликов
COUNTER_FILE = Path("data") / "interest_counter.json"
# файл со счётчиком просмотров
VIEWS_FILE = Path("data") / "views_counter.json"

_lock = threading.Lock()

def load_value(path: Path) -> int:
    """Читаем значение count из указанного JSON-файла."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("count", 0))
    except Exception:
        pass
    return 0


def save_value(path: Path, value: int) -> None:
    """Сохраняем значение count в указанный JSON-файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"count": value}, f, ensure_ascii=False)


@app.route("/")
def index():
    """Увеличиваем просмотры при открытии страницы и отдаём количество кликов на фронт."""
    with _lock:
        views = load_value(VIEWS_FILE) + 1
        save_value(VIEWS_FILE, views)

        interest = load_value(COUNTER_FILE)

    return render_template("index.html", count=interest)


@app.post("/api/interest")
def api_interest():
    """Инкремент счётчика кликов."""
    with _lock:
        current = load_value(COUNTER_FILE) + 1
        save_value(COUNTER_FILE, current)

    return jsonify({"count": current})


@app.get("/api/metrics")
def api_metrics():
    """Возвращает количество просмотров и кликов."""
    with _lock:
        views = load_value(VIEWS_FILE)
        clicks = load_value(COUNTER_FILE)

    return jsonify({
        "views": views,
        "clicks": clicks
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
