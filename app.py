import json
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, make_response

app = Flask(__name__)

# ==== ФАЙЛЫ С МЕТРИКАМИ ====

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# клики по кнопке "интереса" (общие)
CLICKS_FILE = DATA_DIR / "interest_counter.json"

# просмотры по страницам
PAGES = {
    "main": {
        "views": DATA_DIR / "views_main.json",
        "unique": DATA_DIR / "unique_main.json",
    },
    "guide": {
        "views": DATA_DIR / "views_guide.json",
        "unique": DATA_DIR / "unique_guide.json",
    },
    "survey": {
        "views": DATA_DIR / "views_survey.json",
        "unique": DATA_DIR / "unique_survey.json",
    },
}

# результаты опроса
SURVEY_FILE = DATA_DIR / "survey_results.json"

# заявки раннего доступа с лендинга
EARLY_ACCESS_FILE = DATA_DIR / "early_access.json"

_lock = threading.Lock()


# ==== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====

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


def register_visit(page: str) -> tuple[int, str | None]:
    """
    Регистрируем просмотр для конкретной страницы:
      - увеличиваем total views для page
      - считаем уникальный просмотр для page по отдельной cookie
    Возвращаем (clicks, name_cookie_to_set_if_new).

    page ∈ {"main", "guide", "survey"}.
    """
    if page not in PAGES:
        raise ValueError(f"Unknown page '{page}' for metrics")

    views_file = PAGES[page]["views"]
    unique_file = PAGES[page]["unique"]
    visited_cookie_name = f"tl_visited_{page}"

    with _lock:
        # total views для этой страницы
        total_views = load_value(views_file) + 1
        save_value(views_file, total_views)

        # клики (общие)
        clicks = load_value(CLICKS_FILE)

        # уникальные просмотры по этой странице
        has_cookie = request.cookies.get(visited_cookie_name)
        cookie_to_set = None
        if has_cookie is None:
            # первый заход на эту страницу с данного браузера
            unique_views = load_value(unique_file) + 1
            save_value(unique_file, unique_views)
            cookie_to_set = visited_cookie_name
        # если cookie уже есть — не трогаем unique-counter

    return clicks, cookie_to_set


def append_survey_result(payload: dict) -> None:
    """Добавляем одну запись результатов опроса в SURVEY_FILE."""
    with _lock:
        SURVEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if SURVEY_FILE.exists():
            try:
                with open(SURVEY_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        data = loaded
            except Exception:
                data = []

        data.append(payload)

        with open(SURVEY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_survey_data():
    """Читаем сырые ответы опроса (список словарей)."""
    if not SURVEY_FILE.exists():
        return []
    try:
        with open(SURVEY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []

def load_early_access():
    """Читаем список заявок раннего доступа."""
    if not EARLY_ACCESS_FILE.exists():
        return []
    try:
        with open(EARLY_ACCESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def append_early_access(payload: dict) -> None:
    """Добавляем одну заявку раннего доступа."""
    with _lock:
        EARLY_ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        if EARLY_ACCESS_FILE.exists():
            try:
                with open(EARLY_ACCESS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        rows = loaded
            except Exception:
                rows = []
        rows.append(payload)
        with open(EARLY_ACCESS_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)


def build_survey_stats(rows: list[dict]) -> dict:
    """
    Делаем простую агрегацию по опросу:
    - количество ответов
    - распределение usefulness (1–5)
    - распределение llm_usage / ready_to_practice / product_interest
    """
    total = len(rows)
    stats = {
        "total": total,
        "usefulness": {},
        "llm_usage": {},
        "ready_to_practice": {},
        "product_interest": {},
    }

    if total == 0:
        return stats

    def inc(counter: dict, key: str):
        if not key:
            key = "none"  # для пустых/не заполненных
        counter[key] = counter.get(key, 0) + 1

    for row in rows:
        inc(stats["usefulness"], str(row.get("usefulness", "")).strip())
        inc(stats["llm_usage"], row.get("llm_usage", "").strip())
        inc(stats["ready_to_practice"], row.get("ready_to_practice", "").strip())
        inc(stats["product_interest"], row.get("product_interest", "").strip())

    # посчитаем проценты
    def with_percent(counter: dict) -> list[dict]:
        # вернём список словарей: {"value": ..., "count": ..., "percent": ...}
        result = []
        for key, value in counter.items():
            percent = round(value * 100.0 / total, 1)
            result.append({"value": key, "count": value, "percent": percent})
        # чуть отсортируем по count, убывание
        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    stats["usefulness"] = with_percent(stats["usefulness"])
    stats["llm_usage"] = with_percent(stats["llm_usage"])
    stats["ready_to_practice"] = with_percent(stats["ready_to_practice"])
    stats["product_interest"] = with_percent(stats["product_interest"])

    return stats


# ==== РОУТЫ СТРАНИЦ ====

@app.route("/")
def index():
    """
    Главная страница.
    Метрики считаем как page="main".
    """
    clicks, cookie_to_set = register_visit("main")

    # считаем именно количество заявок раннего доступа
    leads = load_early_access()
    count = len(leads)

    resp = make_response(render_template("index.html", count=count))
    if cookie_to_set:
        resp.set_cookie(cookie_to_set, "1", max_age=60 * 60 * 24 * 365, path="/")
    return resp



@app.route("/guide")
def guide():
    """
    Страница-лонгрид по адресу /guide.
    Метрики считаем отдельно как page="guide".
    """
    clicks, cookie_to_set = register_visit("guide")

    # если у тебя отдельный шаблон под guide — замени index.html на guide.html
    resp = make_response(render_template("prompt_guide.html", count=clicks))
    if cookie_to_set:
        resp.set_cookie(cookie_to_set, "1", max_age=60 * 60 * 24 * 365, path="/")
    return resp


@app.route("/survey", methods=["GET", "POST"])
def survey():
    """
    Страница короткого опроса.
    Метрики считаем отдельно как page="survey".
    """
    clicks, cookie_to_set = register_visit("survey")

    if request.method == "POST":
        usefulness = request.form.get("usefulness", "").strip()
        llm_usage = request.form.get("llm_usage", "").strip()
        main_problem = request.form.get("main_problem", "").strip()
        ready_to_practice = request.form.get("ready_to_practice", "").strip()
        product_interest = request.form.get("product_interest", "").strip()
        email = request.form.get("email", "").strip()

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "usefulness": usefulness,
            "llm_usage": llm_usage,
            "main_problem": main_problem,
            "ready_to_practice": ready_to_practice,
            "product_interest": product_interest,
            "email": email,
        }
        append_survey_result(payload)

        resp = make_response(
            render_template("survey.html", submitted=True, count=clicks)
        )
    else:
        resp = make_response(
            render_template("survey.html", submitted=False, count=clicks)
        )

    if cookie_to_set:
        resp.set_cookie(cookie_to_set, "1", max_age=60 * 60 * 24 * 365, path="/")
    return resp


@app.get("/admin")
def admin():
    """
    Простая админ-страничка:
    - метрики по страницам (просмотры / уникальные)
    - общий счётчик кликов
    - статистика и последние ответы по опросу
    """
    with _lock:
        # метрики по страницам
        metrics = {}
        for page, paths in PAGES.items():
            views_total = load_value(paths["views"])
            views_unique = load_value(paths["unique"])
            metrics[page] = {
                "views_total": views_total,
                "views_unique": views_unique,
            }

        clicks = load_value(CLICKS_FILE)

        # опрос
        survey_rows = load_survey_data()

        # заявки раннего доступа
        early_access_rows = load_early_access()

    # статистика по опросу
    survey_stats = build_survey_stats(survey_rows)

    # последние N ответов (например, 20), отсортируем по времени
    def parse_ts(r):
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", ""))
        except Exception:
            return datetime.min

    survey_rows_sorted = sorted(survey_rows, key=parse_ts, reverse=True)
    last_responses = survey_rows_sorted[:20]

    # заявки раннего доступа — сортируем по времени
    def parse_ts_lead(r):
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", ""))
        except Exception:
            return datetime.min

    early_sorted = sorted(early_access_rows, key=parse_ts_lead, reverse=True)
    early_last = early_sorted[:50]

    return render_template(
        "admin.html",
        metrics=metrics,
        clicks=clicks,
        survey_stats=survey_stats,
        last_responses=last_responses,
        early_access_total=len(early_access_rows),
        early_access_last=early_last,
    )


# ==== API ДЛЯ КНОПКИ И МЕТРИК ====

@app.post("/api/interest")
def api_interest():
    """Инкремент счётчика кликов по кнопке (общий, не по страницам)."""
    with _lock:
        current = load_value(CLICKS_FILE) + 1
        save_value(CLICKS_FILE, current)
    return jsonify({"count": current})

@app.post("/api/early-access")
def api_early_access():
    """
    Принимает заявку раннего доступа с лендинга.
    Ожидает JSON: {"email": "...", "consent": true}
    """
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    consent = bool(data.get("consent"))

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "invalid_email"}), 400
    if not consent:
        return jsonify({"ok": False, "error": "no_consent"}), 400

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "email": email,
        "consent": consent,
        "source": "landing",
        "user_agent": request.headers.get("User-Agent", ""),
    }
    append_early_access(payload)

    # обновляем общий счётчик интереса, чтобы /admin и лендинг видели рост
    with _lock:
        current = load_value(CLICKS_FILE) + 1
        save_value(CLICKS_FILE, current)

    leads = load_early_access()
    return jsonify({"ok": True, "count": len(leads)})


@app.get("/api/metrics")
def api_metrics():
    """
    Возвращаем раздельные метрики по страницам + общий счётчик кликов.

    Пример ответа:
    {
      "main":  {"views_total": 10, "views_unique": 7},
      "guide": {"views_total": 5,  "views_unique": 4},
      "survey":{"views_total": 3,  "views_unique": 3},
      "clicks": 8
    }
    """
    with _lock:
        clicks = load_value(CLICKS_FILE)

        result = {}
        for page, paths in PAGES.items():
            views_total = load_value(paths["views"])
            views_unique = load_value(paths["unique"])
            result[page] = {
                "views_total": views_total,
                "views_unique": views_unique,
            }

        result["clicks"] = clicks

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
