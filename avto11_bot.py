import requests, json, time, os, threading, http.server, socketserver
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
PRICE_THRESHOLD_USD = 15000
USD_TO_RUB = 92.0
CHECK_INTERVAL = 300
SEEN_FILE = "seen_ads.json"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
API_URL = "https://auto.ru/api/1.0/search/cars"
API_PARAMS = {"sort": "cr_date-desc", "sort_dir": "desc", "section": "used", "category": "cars", "page": 1, "page_size": 20, "output_type": "list"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36", "Accept": "application/json", "Accept-Language": "ru-RU,ru;q=0.9", "x-client-app": "autoru-mobile-android", "x-client-date": str(int(time.time() * 1000)), "Referer": "https://auto.ru/", "Origin": "https://auto.ru"}

def now():
    return datetime.now().strftime("%H:%M:%S")

def run_web_server():
    PORT = int(os.environ.get("PORT", 8080))
    class Silent(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, *args):
            pass
    with socketserver.TCPServer(("", PORT), Silent) as httpd:
        httpd.serve_forever()

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)

def fetch_listings(session):
    try:
        HEADERS["x-client-date"] = str(int(time.time() * 1000))
        resp = session.get(API_URL, params=API_PARAMS, headers=HEADERS, timeout=20)
        if resp.status_code == 403 or "showcaptcha" in resp.url:
            print(f"[{now()}] Капча. Жду 10 минут...")
            time.sleep(600)
            return []
        resp.raise_for_status()
        return resp.json().get("offers", [])
    except Exception as e:
        print(f"[{now()}] Ошибка: {e}")
        return []

def parse_offer(offer):
    try:
        ad_id = offer.get("id", "")
        url = "https://auto.ru" + offer.get("url", "")
        price_rub = int(offer.get("price_info", {}).get("price", 0))
        price_usd = round(price_rub / USD_TO_RUB) if price_rub else 0
        veh = offer.get("vehicle_info", {})
        mark = veh.get("mark_info", {}).get("name", "")
        model = veh.get("model_info", {}).get("name", "")
        year = offer.get("documents", {}).get("year", "")
        tech = veh.get("tech_param", {})
        disp = tech.get("displacement", 0)
        disp_l = f"{round(disp/1000, 1)}" if disp else ""
        trans = {"AUTOMATIC": "AT", "MANUAL": "MT", "ROBOT": "Робот", "VARIATOR": "CVT"}.get(tech.get("transmission", ""), "")
        tech_str = " ".join(filter(None, [disp_l, trans]))
        name = " ".join(filter(None, [mark, model, str(year)]))
        return {"id": ad_id, "url": url, "name": name or "Без названия", "tech": tech_str, "price_rub": price_rub, "price_usd": price_usd}
    except:
        return None

def send_message(text):
    try:
        resp = requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}, timeout=15)
        if not resp.ok:
            print(f"[{now()}] Telegram error: {resp.text}")
    except Exception as e:
        print(f"[{now()}] Ошибка Telegram: {e}")

def format_message(ad):
    usd, rub = ad["price_usd"], ad["price_rub"]
    label = f"🟢 <b>Ниже {PRICE_THRESHOLD_USD:,}$!</b>" if usd and usd <= PRICE_THRESHOLD_USD else f"🔴 <b>Выше {PRICE_THRESHOLD_USD:,}$</b>" if usd else "⚪️ <b>Новое объявление</b>"
    price_line = f"💰 <b>{usd:,} $</b> (~{rub:,} ₽)" if rub else "💰 Цена не указана"
    return "\n".join([label, f"🚗 {ad['name']}" + (f", {ad['tech']}" if ad["tech"] else ""), price_line, f'🔗 <a href="{ad["url"]}">Смотреть объявление</a>'])

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    print(f"[{now()}] Бот запущен")
    send_message("✅ <b>Бот запущен</b>\nОтслеживаю новые объявления на Avto.ru.")
    seen = load_seen()
    session = requests.Session()
    while True:
        print(f"[{now()}] Проверяю...")
        for raw in fetch_listings(session):
            ad = parse_offer(raw)
            if not ad or ad["id"] in seen:
                continue
            seen.add(ad["id"])
            send_message(format_message(ad))
            time.sleep(1)
        save_seen(seen)
        print(f"[{now()}] Жду {CHECK_INTERVAL//60} мин.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
