"""store.py — Danh sách knee đã lưu (tên + toàn bộ thông số), lưu ở knee_saved.json."""

from __future__ import annotations

import copy
import json
import os
import time

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knee_saved.json")


class SavedList:
    def __init__(self, path: str = PATH):
        self.path = path
        self.items: list[dict] = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = data if isinstance(data, list) else []
        except (OSError, ValueError):
            self.items = []

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, name: str, state: dict, summary: dict) -> int:
        self.items.append(dict(name=name, state=copy.deepcopy(state), summary=summary, time=time.strftime("%d/%m/%Y %H:%M")))
        self.save()
        return len(self.items) - 1

    def update(self, i: int, state: dict, summary: dict):
        self.items[i].update(state=copy.deepcopy(state), summary=summary, time=time.strftime("%d/%m/%Y %H:%M"))
        self.save()

    def rename(self, i: int, name: str):
        self.items[i]["name"] = name
        self.items[i]["state"]["name"] = name
        self.save()

    def delete(self, i: int):
        del self.items[i]
        self.save()

    def move(self, i: int, step: int) -> int:
        j = i + step
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.save()
            return j
        return i
