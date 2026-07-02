# -*- coding: utf-8 -*-
"""
Telegram-бот для поиска телефонов и макбуков на Kufar.by по заданным
пользователем параметрам (цена + ключевые слова).

Команды бота:

/start              — приветствие и краткая инструкция
/phone              — задать поиск телефонов:
                      /phone <мин_цена> <макс_цена> [ключевые слова]
                      пример: /phone 200 500 iphone 13
/macbook            — задать поиск макбуков:
                      /macbook <мин_цена> <макс_цена> [ключевые слова]
                      пример: /macbook 600 1200 air m1
/stop_phone         — выключить поиск телефонов
/stop_macbook       — выключить поиск макбуков
/status             — показать текущие фильтры
/check              — проверить прямо сейчас, не дожидаясь автопроверки

Цены указываются в долларах США (Kufar отдаёт цену в BYN и USD, бот
сравнивает по USD — это самый стабильный вариант для пользователя не из Беларуси).

Как это работает:
- Бот раз в CHECK_INTERVAL_SECONDS секунд опрашивает Kufar по каждой
  включённой у пользователя категории.
- Из выдачи оставляются объявления, у которых цена входит в заданный диапазон
  и (если заданы ключевые слова) заголовок содержит хотя бы одно из них.
- Уже показанные объявления запоминаются, чтобы не дублировать уведомления.
"""

import logging
import os
import re
import threading
import time

import telebot
from telebot import types

import kufar_api
import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("kufar_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit(
        "Не задан токен бота. Установите переменную окружения BOT_TOKEN "
        "(токен получают у @BotFather в Telegram)."
    )

CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))  # 5 минут

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# --------------------------------------------------------------------------
# Разбор команд
# --------------------------------------------------------------------------

def parse_filter_args(text: str):
    """
    Разбирает аргументы вида "200 500 iphone 13" ->
    (min_price=200.0, max_price=500.0, keywords=["iphone", "13"])
    Возвращает None, если формат неверный.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None
    try:
        min_price = float(parts[0])
        max_price = float(parts[1])
    except ValueError:
        return None
    if min_price > max_price:
        min_price, max_price = max_price, min_price
    keywords = [p.lower() for p in parts[2:]]
    return {"min": min_price, "max": max_price, "keywords": keywords}


def strip_command(text: str, command: str) -> str:
    return re.sub(rf"^/{command}(@\w+)?\s*", "", text, flags=re.IGNORECASE)


# --------------------------------------------------------------------------
# Хендлеры команд
# --------------------------------------------------------------------------

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        "Привет! Я слежу за объявлениями на Kufar.by и присылаю новые "
        "телефоны и макбуки по твоим параметрам.\n\n"
        "<b>Настроить поиск телефонов:</b>\n"
        "<code>/phone мин_цена макс_цена [ключевые слова]</code>\n"
        "Пример: <code>/phone 200 500 iphone 13</code>\n\n"
        "<b>Настроить поиск макбуков:</b>\n"
        "<code>/macbook мин_цена макс_цена [ключевые слова]</code>\n"
        "Пример: <code>/macbook 600 1200 air m1</code>\n\n"
        "Цены указывай в долларах США.\n\n"
        "Другие команды:\n"
        "/status — показать текущие фильтры\n"
        "/check — проверить объявления прямо сейчас\n"
        "/stop_phone — выключить поиск телефонов\n"
        "/stop_macbook — выключить поиск макбуков"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["phone"])
def cmd_phone(message):
    args = strip_command(message.text, "phone")
    parsed = parse_filter_args(args)
    if parsed is None:
        bot.reply_to(
            message,
            "Формат: /phone мин_цена макс_цена [ключевые слова]\n"
            "Пример: /phone 200 500 iphone 13",
        )
        return
    storage.set_filter(message.chat.id, "phones", parsed)
    kw = f", ключевые слова: {', '.join(parsed['keywords'])}" if parsed["keywords"] else ""
    bot.reply_to(
        message,
        f"Ок! Ищу телефоны от {parsed['min']:.0f}$ до {parsed['max']:.0f}$" + kw,
    )


@bot.message_handler(commands=["macbook"])
def cmd_macbook(message):
    args = strip_command(message.text, "macbook")
    parsed = parse_filter_args(args)
    if parsed is None:
        bot.reply_to(
            message,
            "Формат: /macbook мин_цена макс_цена [ключевые слова]\n"
            "Пример: /macbook 600 1200 air m1",
        )
        return
    storage.set_filter(message.chat.id, "macbooks", parsed)
    kw = f", ключевые слова: {', '.join(parsed['keywords'])}" if parsed["keywords"] else ""
    bot.reply_to(
        message,
        f"Ок! Ищу макбуки от {parsed['min']:.0f}$ до {parsed['max']:.0f}$" + kw,
    )


@bot.message_handler(commands=["stop_phone"])
def cmd_stop_phone(message):
    storage.clear_filter(message.chat.id, "phones")
    bot.reply_to(message, "Поиск телефонов выключен.")


@bot.message_handler(commands=["stop_macbook"])
def cmd_stop_macbook(message):
    storage.clear_filter(message.chat.id, "macbooks")
    bot.reply_to(message, "Поиск макбуков выключен.")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    user = storage.get_user(message.chat.id)
    lines = []

    phones = user.get("phones")
    if phones:
        kw = f", ключевые слова: {', '.join(phones['keywords'])}" if phones["keywords"] else ""
        lines.append(f"📱 Телефоны: {phones['min']:.0f}$–{phones['max']:.0f}${kw}")
    else:
        lines.append("📱 Телефоны: не настроено")

    macbooks = user.get("macbooks")
    if macbooks:
        kw = f", ключевые слова: {', '.join(macbooks['keywords'])}" if macbooks["keywords"] else ""
        lines.append(f"💻 Макбуки: {macbooks['min']:.0f}$–{macbooks['max']:.0f}${kw}")
    else:
        lines.append("💻 Макбуки: не настроено")

    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["check"])
def cmd_check(message):
    bot.reply_to(message, "Проверяю прямо сейчас...")
    run_check_for_user(message.chat.id)


# --------------------------------------------------------------------------
# Логика поиска и уведомлений
# --------------------------------------------------------------------------

def ad_matches_keywords(ad: dict, keywords: list) -> bool:
    if not keywords:
        return True
    subject = ad["subject"].lower()
    return any(kw in subject for kw in keywords)


def send_ad(chat_id: int, ad: dict, label: str):
    caption = (
        f"{label}\n"
        f"<b>{ad['subject']}</b>\n"
        f"💵 {ad['price_usd']:.0f}$ ({ad['price_byn']:.0f} BYN)\n"
        f"{ad['link']}"
    )
    try:
        if ad["image_url"]:
            bot.send_photo(chat_id, ad["image_url"], caption=caption)
        else:
            bot.send_message(chat_id, caption)
    except Exception as e:
        log.warning("Не удалось отправить фото, отправляю текстом: %s", e)
        bot.send_message(chat_id, caption)


def check_category(chat_id: int, filter_cfg: dict, category: int, label: str, query: str = ""):
    try:
        raw_ads = kufar_api.search_ads(category=category, query=query)
    except Exception as e:
        log.warning("Ошибка запроса к Kufar (%s): %s", label, e)
        return

    new_ids = []
    for raw in raw_ads:
        ad = kufar_api.parse_ad(raw)
        if not ad["id"] or storage.is_seen(chat_id, ad["id"]):
            continue
        if not (filter_cfg["min"] <= ad["price_usd"] <= filter_cfg["max"]):
            continue
        if not ad_matches_keywords(ad, filter_cfg["keywords"]):
            continue

        send_ad(chat_id, ad, label)
        new_ids.append(ad["id"])
        time.sleep(0.5)  # не спамим Telegram API

    if new_ids:
        storage.mark_seen(chat_id, new_ids)


def run_check_for_user(chat_id: int):
    user = storage.get_user(chat_id)

    if user.get("phones"):
        check_category(
            chat_id, user["phones"], kufar_api.CATEGORY_PHONES,
            "📱 Новый телефон", query="",
        )

    if user.get("macbooks"):
        # ноутбуки Kufar.by держит все в одной категории, поэтому дополнительно
        # просим у Kufar только "macbook" в тексте объявления
        check_category(
            chat_id, user["macbooks"], kufar_api.CATEGORY_LAPTOPS,
            "💻 Новый макбук", query="macbook",
        )


def background_loop():
    while True:
        try:
            users = storage.get_all_users()
            for chat_id_str in list(users.keys()):
                run_check_for_user(int(chat_id_str))
        except Exception as e:
            log.exception("Ошибка в фоновом цикле проверки: %s", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    log.info("Бот запущен, проверка каждые %s секунд", CHECK_INTERVAL_SECONDS)
    threading.Thread(target=background_loop, daemon=True).start()
    bot.infinity_polling()
