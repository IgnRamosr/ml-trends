"""
Recolecta snapshots de productos "best seller" por categoría desde la API
de Mercado Libre (endpoint highlights) y los guarda en SQLite.
Pensado para correr 1 vez al día (cron/Task Scheduler).
"""

import os
import sqlite3
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["ML_CLIENT_ID"]
CLIENT_SECRET = os.environ["ML_CLIENT_SECRET"]

SITE = "MLC"  # Chile
DB_PATH = "ml_trends.db"

# Categorías a monitorear (id, nombre). Ver lista completa en
# https://api.mercadolibre.com/sites/MLC/categories
CATEGORIES = [
    ("MLC1338", "Fitness y Musculacion"),
    ("MLC1292", "Ciclismo"),
    ("MLC158310", "Accesorios de Moda"),
    ("MLC158467", "Poleras"),
    ("MLC440687", "Ropa Deportiva"),
    ("MLC1592", "Cocina y Menaje"),
    ("MLC1631", "Adornos y Decoracion del Hogar"),
    ("MLC3813", "Accesorios para Celulares"),
    ("MLC417704", "Smartwatches y Accesorios"),
    ("MLC1055", "Celulares y Smartphones"),
    ("MLC1010", "Audio"),
    ("MLC157767", "Drones y Accesorios"),
    ("MLC447778", "Accesorios para PC Gaming"),
]


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            category_id TEXT NOT NULL,
            category_name TEXT NOT NULL,
            position INTEGER,
            product_id TEXT,
            item_id TEXT,
            title TEXT,
            price REAL,
            condition TEXT,
            permalink TEXT
        )
        """
    )
    conn.commit()


def get_access_token() -> str:
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_best_sellers(category_id: str, token: str) -> list[dict]:
    url = f"https://api.mercadolibre.com/highlights/{SITE}/category/{category_id}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("content", [])


def fetch_product_summary(product_id: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}

    product_resp = requests.get(
        f"https://api.mercadolibre.com/products/{product_id}",
        headers=headers,
        timeout=15,
    )
    product_resp.raise_for_status()
    product = product_resp.json()

    items_resp = requests.get(
        f"https://api.mercadolibre.com/products/{product_id}/items",
        headers=headers,
        timeout=15,
    )
    items_resp.raise_for_status()
    items = items_resp.json().get("results", [])
    cheapest = min(items, key=lambda it: it["price"]) if items else {}

    return {
        "title": product.get("name"),
        "price": cheapest.get("price"),
        "item_id": cheapest.get("item_id"),
        "condition": cheapest.get("condition"),
        "permalink": product.get("permalink"),
    }


def save_results(
    conn: sqlite3.Connection,
    category_id: str,
    category_name: str,
    highlights: list[dict],
    token: str,
) -> None:
    captured_at = datetime.now().isoformat(timespec="seconds")
    rows = []
    for h in highlights:
        if h.get("type") != "PRODUCT":
            continue
        product_id = h["id"]
        try:
            summary = fetch_product_summary(product_id, token)
        except requests.RequestException as e:
            print(f"  [WARN] no se pudo obtener detalle de {product_id}: {e}")
            continue
        rows.append(
            (
                captured_at,
                category_id,
                category_name,
                h.get("position"),
                product_id,
                summary.get("item_id"),
                summary.get("title"),
                summary.get("price"),
                summary.get("condition"),
                summary.get("permalink"),
            )
        )
        time.sleep(0.3)  # evitar martillar la API

    conn.executemany(
        """
        INSERT INTO snapshots
            (captured_at, category_id, category_name, position, product_id,
             item_id, title, price, condition, permalink)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    token = get_access_token()

    for category_id, category_name in CATEGORIES:
        try:
            highlights = fetch_best_sellers(category_id, token)
            save_results(conn, category_id, category_name, highlights, token)
            print(f"[OK] {category_name}: {len(highlights)} best sellers guardados")
        except requests.RequestException as e:
            print(f"[ERROR] {category_name}: {e}")
        time.sleep(1)

    conn.close()


if __name__ == "__main__":
    main()
