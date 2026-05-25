import sys
sys.stdout.reconfigure(line_buffering=True)
import requests, json, time, os, threading, http.server, socketserver
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
PRICE_THRESHOLD_USD = 15000
CHECK_INTERVAL = 300
SEEN_FILE = "seen_ads.json"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
KRW_RATE = 1350  # запасной курс если API недоступен

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://www.encar.com/",
}

def now():
    return datetime.now().strftime("%H:%M:%S")

def get_krw_rate():
    try:
        resp = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        rate = resp.json()["rates"]["KRW"]
        print(f"[{now()}] Курс USD/KRW: {rate:.0f}", flush=True)
        return rate
    except Exception as e:
        print(f"[{now()}] Не удалось получить курс: {e}. Использую {KRW_RATE}", flush=True)
        return KRW_RATE

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

def fetch_listings():
    try:
        print(f"[{now()}] Запрос к Encar...", flush=True)
        url = "http://api.encar.com/search/car/list/general?count=true&q=(And.Hidden.N._.CarType.Y.)&sr=%7CModifiedDate%7C0%7C50"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"[{now()}] Encar: {resp.status_code}", flush=True)
        if resp.status_code == 200:
            items = resp.json().get("SearchResults", [])
            print(f"[{now()}] Получено: {len(items)}", flush=True)
            return items
        return []
    except Exception as e:
        print(f"[{now()}] Ошибка: {e}", flush=True)
        return []

def parse_offer(item, rate):
    try:
        ad_id = str(item.get("Id", ""))
        manufacturer = item.get("Manufacturer", "")
        model = item.get("Model", "")
        badge = item.get("Badge", "")
        year = item.get("Year", "")
        price_krw = item.get("Price", 0) * 10000
        price_usd = round(price_krw / rate) if price_krw else 0
        url = f"https://www.encar.com/dc/dc_cardetailview.do?carid={ad_id}"
        name = " ".join(filter(None, [manufacturer, model, badge, str(year)]))
        return {"id": ad_id, "name": name or "Без названия", "price_krw": price_krw, "price_usd": price_usd, "url": url}
    except:
        return None

def send_message(text):
    try:
        resp = requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": CHANNEL_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": False,
        }, timeout=15)
        if not resp.ok:
            print(f"[{now()}] Telegram error: {resp.text}", flush=True)
    except Exception as e:
        print(f"[{now()}] Ошибка Telegram: {e}", flush=True)

def format_message(ad, rate):
    usd = ad["price_usd"]
    krw = ad["price_krw"]
    label = f"🟢 <b>Ниже {PRICE_THRESHOLD_USD:,}$!</b>" if usd and usd <= PRICE_THRESHOLD_USD else f"🔴 <b>Выше {PRICE_THRESHOLD_USD:,}$</b>" if usd else "⚪️ <b>Новое объявление</b>"
    price_line = f"💰 <b>{usd:,} $</b> (~{krw:,} ₩)" if krw else "💰 Цена не указана"
    rate_line = f"📈 Курс: 1$ = {rate:.0f} ₩"
    return "\n".join([label, f"🚗 {ad['name']}", price_line, rate_line, f'🔗 <a href="{ad["url"]}">Смотреть на Encar</a>'])

def main():
    print("=== БОТ СТАРТУЕТ ===", flush=True)
    threading.Thread(target=run_web_server, daemon=True).start()
    send_message("✅ <b>Бот запущен</b>\nОтслеживаю новые объявления на Encar.com 🇰🇷")
    seen = load_seen()
    first_run = len(seen) == 0
    rate_update_counter = 0

    rate = get_krw_rate()

    while True:
        # Обновляем курс каждые 6 проверок (каждые 30 минут)
        rate_update_counter += 1
        if rate_update_counter >= 6:
            rate = get_krw_rate()
            rate_update_counter = 0

        print(f"[{now()}] Проверяю Encar... (курс: {rate:.0f} ₩)", flush=True)
        ads = fetch_listings()
        new_count = 0

        for item in ads:
            ad = parse_offer(item, rate)
            if not ad or ad["id"] in seen:
                continue
            seen.add(ad["id"])
            if first_run:
                continue
            send_message(format_message(ad, rate))
            new_count += 1
            time.sleep(4)

        if first_run:
            print(f"[{now()}] Первый запуск — запомнили {len(seen)} объявлений.", flush=True)
            send_message(f"👀 Запомнил {len(seen)} текущих объявлений. Буду слать только новые!")
            first_run = False

        save_seen(seen)
        print(f"[{now()}] Новых: {new_count}. Жду {CHECK_INTERVAL//60} мин.", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
