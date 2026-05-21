import requests, json, time, os, threading, http.server, socketserver
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
PRICE_THRESHOLD_USD = 15000
USD_TO_RUB = 92.0
CHECK_INTERVAL = 300
SEEN_FILE = "seen_ads.json"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

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

def fetch_listings():
    try:
        url = "https://www.avito.ru/api/9/items?categoryId=9&locationId=0&sort=date&order=d&count=50&page=1"
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("items", [])
        print(f"[{now()}] Авито вернул: {resp.status_code}")
        return []
    except Exception as e:
        print(f"[{now()}] Ошибка: {e}")
        return []

def parse_offer(item):
    try:
        ad_id = str(item.get("id", ""))
        title = item.get("title", "Без названия")
        price_rub = item.get("priceDetailed", {}).get("value", 0)
        price_usd = round(price_rub / USD_TO_RUB) if price_rub else 0
        url = "https://www.avito.ru" + item.get("urlPath", "")
        return {"id": ad_id, "name": title, "price_rub": price_rub, "price_usd": price_usd, "url": url}
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
    return "\n".join([label, f"🚗 {ad['name']}", price_line, f'🔗 <a href="{ad["url"]}">Смотреть на Авито</a>'])

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    print(f"[{now()}] Бот запущен")
    send_message("✅ <b>Бот запущен</b>\nОтслеживаю новые объявления на Авито.")
    seen = load_seen()
    while True:
        print(f"[{now()}] Проверяю Авито...")
        ads = fetch_listings()
        print(f"[{now()}] Найдено: {len(ads)}")
        new_count = 0
        for item in ads:
            ad = parse_offer(item)
            if not ad or ad["id"] in seen:
                continue
            seen.add(ad["id"])
            send_message(format_message(ad))
            new_count += 1
            time.sleep(1)
        save_seen(seen)
        print(f"[{now()}] Новых: {new_count}. Жду {CHECK_INTERVAL//60} мин.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
