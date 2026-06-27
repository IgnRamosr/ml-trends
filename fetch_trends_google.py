"""
Recolecta interés de búsqueda (Google Trends) por categoría en Chile
y lo guarda en SQLite. Complementa los datos de Mercado Libre, ya que
permite comparar demanda relativa ENTRE categorías (cosa que la API de
ML no permite en su tier gratuito).
"""

import sqlite3
from datetime import datetime

from pytrends.request import TrendReq

from trends_helper import fetch_comparable_interest

DB_PATH = "ml_trends.db"
GEO = "CL"
TIMEFRAME = "today 12-m"

# Palabras clave representativas de cada categoría monitoreada en fetch_trends.py
CATEGORY_KEYWORDS = {
    "Tecnologia": "tecnologia",
    "Deportes y Fitness": "deportes",
    "Ropa y Accesorios": "ropa",
    "Hogar y Muebles": "muebles",
    "Celulares y Telefonos": "celulares",
    "Electronica, Audio y Video": "electronica",
}


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trends_google (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            category_name TEXT NOT NULL,
            keyword TEXT NOT NULL,
            interest_score INTEGER
        )
        """
    )
    conn.commit()


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    pytrends = TrendReq(hl="es-CL", tz=240)
    captured_at = datetime.now().isoformat(timespec="seconds")
    keywords = list(CATEGORY_KEYWORDS.values())

    df = fetch_comparable_interest(pytrends, keywords, GEO, TIMEFRAME)
    avg_interest = df[keywords].mean()

    rows = [
        (captured_at, category_name, keyword, round(avg_interest[keyword]))
        for category_name, keyword in CATEGORY_KEYWORDS.items()
    ]

    conn.executemany(
        """
        INSERT INTO trends_google (captured_at, category_name, keyword, interest_score)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    print(f"[OK] {len(rows)} categorías guardadas con interés promedio de los últimos 12 meses")


if __name__ == "__main__":
    main()
