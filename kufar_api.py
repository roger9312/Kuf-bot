# -*- coding: utf-8 -*-
"""
Клиент для неофициального публичного API Kufar.by.

Kufar не публикует официальную документацию API, поэтому здесь используется
эндпоинт, которым пользуется сам сайт kufar.by (search-api). Он может
измениться без предупреждения — в этом случае нужно будет поправить BASE_URL
и/или названия полей в ответе (см. функцию parse_ad).
"""

import requests

BASE_URL = "https://api.kufar.by/search-api/v1/search/rendered-paginated"

# Категории Kufar (числовые id, как их использует сайт).
CATEGORY_PHONES = 17010   # Мобильные телефоны
CATEGORY_LAPTOPS = 16040  # Ноутбуки (macbook ищем внутри неё по ключевому слову)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def search_ads(category: int, query: str = "", size: int = 40) -> list:
    """
    Возвращает список объявлений (сырые словари из ответа Kufar) для заданной
    категории и (опционально) текстового запроса.

    Фильтрацию по цене и по ключевым словам делаем на своей стороне (в bot.py),
    т.к. форматы параметров цены в неофициальном API нестабильны и часто меняются.
    """
    params = {
        "size": size,
        "lang": "ru",
        "cat": category,
    }
    if query:
        params["query"] = query

    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("ads", [])


def parse_ad(raw: dict) -> dict:
    """
    Приводит сырое объявление Kufar к простому и предсказуемому виду.
    Поля у Kufar могут называться по-разному в разных выдачах, поэтому
    берём с запасными вариантами (fallback).
    """
    ad_id = raw.get("ad_id") or raw.get("id")

    subject = (
        raw.get("subject")
        or raw.get("title")
        or raw.get("name")
        or "Без названия"
    )

    price_byn = raw.get("price_byn")
    price_usd = raw.get("price_usd")

    try:
        price_byn = float(price_byn) / 100 if price_byn and float(price_byn) > 100000 else float(price_byn or 0)
    except (TypeError, ValueError):
        price_byn = 0.0
    try:
        price_usd = float(price_usd) / 100 if price_usd and float(price_usd) > 100000 else float(price_usd or 0)
    except (TypeError, ValueError):
        price_usd = 0.0

    image_url = None
    images = raw.get("images") or []
    if images:
        img = images[0]
        path = img.get("path")
        if path:
            image_url = f"https://rms.kufar.by/v1/gallery/{path}"

    link = f"https://www.kufar.by/item/{ad_id}" if ad_id else None

    return {
        "id": str(ad_id),
        "subject": subject,
        "price_byn": price_byn,
        "price_usd": price_usd,
        "image_url": image_url,
        "link": link,
    }
