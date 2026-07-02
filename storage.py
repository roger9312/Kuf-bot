# -*- coding: utf-8 -*-
"""
Простое хранилище на JSON-файле: фильтры пользователей и уже увиденные
объявления (чтобы не присылать одно и то же дважды).
"""

import json
import os
import threading

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

_lock = threading.Lock()


def _default_data() -> dict:
    return {"users": {}}


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        return _default_data()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return _default_data()


def _save(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(chat_id: int) -> dict:
    with _lock:
        data = _load()
        user = data["users"].get(str(chat_id))
        if user is None:
            user = {
                "phones": None,   # {"min":.., "max":.., "keywords": [...]}
                "macbooks": None, # {"min":.., "max":.., "keywords": [...]}
                "seen_ids": [],
            }
            data["users"][str(chat_id)] = user
            _save(data)
        return user


def set_filter(chat_id: int, filter_name: str, filter_value: dict) -> None:
    with _lock:
        data = _load()
        user = data["users"].setdefault(str(chat_id), {
            "phones": None, "macbooks": None, "seen_ids": [],
        })
        user[filter_name] = filter_value
        _save(data)


def clear_filter(chat_id: int, filter_name: str) -> None:
    with _lock:
        data = _load()
        user = data["users"].get(str(chat_id))
        if user:
            user[filter_name] = None
            _save(data)


def get_all_users() -> dict:
    with _lock:
        data = _load()
        return data["users"]


def mark_seen(chat_id: int, ad_ids: list) -> None:
    with _lock:
        data = _load()
        user = data["users"].setdefault(str(chat_id), {
            "phones": None, "macbooks": None, "seen_ids": [],
        })
        seen = set(user.get("seen_ids", []))
        seen.update(ad_ids)
        # ограничим размер истории, чтобы файл не рос бесконечно
        user["seen_ids"] = list(seen)[-3000:]
        _save(data)


def is_seen(chat_id: int, ad_id: str) -> bool:
    with _lock:
        data = _load()
        user = data["users"].get(str(chat_id))
        if not user:
            return False
        return ad_id in set(user.get("seen_ids", []))
