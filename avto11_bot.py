import requests
import json
import time
import os
from datetime import datetime

# ============================================================
#   НАСТРОЙКИ
# ============================================================

BOT_TOKEN  = "8044357740:AAFTcGp_p90C40Eh8XLsx43LILxc74RcfRc"
CHANNEL_ID = "-1003940862314"

# Порог цены в долларах
PRICE_THRESHOLD_USD = 15000

# Курс доллара к рублю
USD_TO_RUB = 92.0

# Как часто проверять (в секундах)
CHECK_INTERVAL = 300

# ============================================================
#   КОД БОТА
# ============================================================

SEEN_FILE    = "seen_ads.json"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Мобильное API Avto.ru — реже блокируется
API_URL = "https://auto.ru/api/1.0/search/cars"
API_PARAMS = {
    "sort":          "cr_date-desc",
    "sort_dir":      "desc",
    "section":       "used",
    "category":      "cars",
    "page":          1,
    "page_size":     20,
    "output_type":   "list",
}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "x-client-app":   "autoru-mobile-android",
    "x-client-date":  str(int(time.time() * 1000)),
    "Referer":        "https://auto.ru/",
    "Origin":         "https://auto.ru",
}


def now():
    return datetime.now().strftime("%H:%M:%S")


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def fetch_listings(session: requests.Session):
    """Получить свежие объявления через API Avto.ru."""
    try:
        HEADERS["x-client-date"] = str(int(time.time() * 1000))
        resp = session.get(API_URL, params=API_PARAMS, headers=HEADERS, timeout=20)

        if resp.status_code == 403 or "showcaptcha" in resp.url:
            print(f"[{now()}] Avto.ru требует капчу. Жду 10 минут...")
            time.sleep(600)
            return []

        resp.raise_for_status()
        data   = resp.json()
        offers = data.get("offers", [])
        return offers

    except Exception as e:
        print(f"[{now()}] Ошибка при получении данных: {e}")
        return []


def parse_offer(offer: dict):
    """Разобрать одно объявление."""
    try:
        ad_id     = offer.get("id", "")
        url       = "https://auto.ru" + offer.get("url", "")
        price_rub = int(offer.get("price_info", {}).get("price", 0))
        price_usd = round(price_rub / USD_TO_RUB) if price_rub else 0

        veh   = offer.get("vehicle_info", {})
        mark  = veh.get("mark_info",  {}).get("name", "")
        model = veh.get("model_info", {}).get("name", "")
        year  = offer.get("documents", {}).get("year", "")

        tech  = veh.get("tech_param", {})
        disp  = tech.get("displacement", 0)
        disp_l = f"{round(disp/1000, 1)}" if disp else ""
        trans  = {"AUTOMATIC": "AT", "MANUAL": "MT", "ROBOT": "Робот",
                  "VARIATOR": "CVT"}.get(tech.get("transmission", ""), "")
        tech_str = " ".join(filter(None, [disp_l, trans]))

        name = " ".join(filter(None, [mark, model, str(year)]))
        return {
            "id":        ad_id,
            "url":       url,
            "name":      name or "Без названия",
            "tech":      tech_str,
            "price_rub": price_rub,
            "price_usd": price_usd,
        }
    except Exception as e:
        print(f"[{now()}] Ошибка разбора объявления: {e}")
        return None


def send_message(text: str):
    url     = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id":                  CHANNEL_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if not resp.ok:
            print(f"[{now()}] Telegram error: {resp.text}")
    except Exception as e:
        print(f"[{now()}] Ошибка Telegram: {e}")


def format_message(ad: dict) -> str:
    usd = ad["price_usd"]
    rub = ad["price_rub"]

    if usd and usd <= PRICE_THRESHOLD_USD:
        label = f"🟢 <b>Ниже {PRICE_THRESHOLD_USD:,}$ — выгодно!</b>"
    elif usd:
        label = f"🔴 <b>Выше {PRICE_THRESHOLD_USD:,}$</b>"
    else:
        label = "⚪️ <b>Новое объявление</b>"

    name_line  = f"🚗 {ad['name']}" + (f", {ad['tech']}" if ad["tech"] else "")
    price_line = (f"💰 <b>{usd:,} $</b>  (~{rub:,} ₽)" if rub
                  else "💰 Цена не указана")
    link_line  = f'🔗 <a href="{ad["url"]}">Смотреть объявление</a>'

    return "\n".join([label, name_line, price_line, link_line])


def main():
    print(f"[{now()}] Бот запущен | канал {CHANNEL_ID}")
    print(f"[{now()}] Интервал: {CHECK_INTERVAL//60} мин | Порог: {PRICE_THRESHOLD_USD:,}$")
    send_message("✅ <b>Бот запущен</b>\nОтслеживаю новые объявления на Avto.ru.")

    seen    = load_seen()
    session = requests.Session()   # сессия сохраняет куки между запросами
    print(f"[{now()}] Известных объявлений: {len(seen)}")

    while True:
        print(f"[{now()}] Проверяю...")
        raw_offers = fetch_listings(session)
        new_count  = 0

        for raw in raw_offers:
            ad = parse_offer(raw)
            if not ad or ad["id"] in seen:
                continue

            seen.add(ad["id"])
            send_message(format_message(ad))
            new_count += 1
            time.sleep(1)

        save_seen(seen)
        print(f"[{now()}] Новых: {new_count}. Следующая проверка через {CHECK_INTERVAL//60} мин.")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
