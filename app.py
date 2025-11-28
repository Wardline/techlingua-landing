import json
import threading
import uuid
from pathlib import Path

from flask import Flask, render_template, jsonify, request, make_response

app = Flask(__name__)

# файлы со счётчиками
CLICKS_FILE = Path("data") / "interest_counter.json"       # клики по кнопке
VIEWS_FILE = Path("data") / "views_counter.json"           # все просмотры (total)
UNIQUE_VIEWS_FILE = Path("data") / "unique_views.json"     # уникальные просмотры

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
    """
    При каждом заходе:
      - увеличиваем общий счётчик просмотров (total views)
      - при отсутствии куки visitor_id считаем уникальный просмотр и ставим куку
    На лендинг отправляем только count кликов.
    """
    with _lock:
        # total views
        total_views = load_value(VIEWS_FILE) + 1
        save_value(VIEWS_FILE, total_views)

        # клики
        clicks = load_value(CLICKS_FILE)

        # проверяем, есть ли у пользователя наша кука
        visitor_id = request.cookies.get("tl_visitor_id")
        is_new_visitor = visitor_id is None

        if is_new_visitor:
            # инкрементируем уникальные просмотры
            unique_views = load_value(UNIQUE_VIEWS_FILE) + 1
            save_value(UNIQUE_VIEWS_FILE, unique_views)
            # создаём новый visitor_id
            visitor_id = str(uuid.uuid4())
        else:
            unique_views = load_value(UNIQUE_VIEWS_FILE)

    # формируем ответ и (при необходимости) ставим куку
    resp = make_response(render_template("index.html", count=clicks))
    # кука живёт год, меняй max_age при желании
    resp.set_cookie("tl_visitor_id", visitor_id, max_age=60 * 60 * 24 * 365, path="/")
    return resp


@app.post("/api/interest")
def api_interest():
    """Инкремент счётчика кликов по кнопке."""
    with _lock:
        current = load_value(CLICKS_FILE) + 1
        save_value(CLICKS_FILE, current)

    return jsonify({"count": current})


@app.get("/api/metrics")
def api_metrics():
    """Возвращаем все три метрики: total views, unique views, clicks."""
    with _lock:
        total_views = load_value(VIEWS_FILE)
        unique_views = load_value(UNIQUE_VIEWS_FILE)
        clicks = load_value(CLICKS_FILE)

    return jsonify(
        {
            "views_total": total_views,
            "views_unique": unique_views,
            "clicks": clicks,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
