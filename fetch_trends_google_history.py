"""
Trae el histórico de 5 años de interés de búsqueda (Google Trends) por
categoría en Chile y lo guarda en SQLite. A diferencia de
fetch_trends_google.py (que guarda un promedio puntual), este script
guarda la serie de tiempo completa para poder comparar año contra año.

Basta correrlo una vez y luego de tanto en tanto (ej. 1 vez al mes) para
refrescar los últimos puntos.
"""

import sqlite3

from pytrends.request import TrendReq

from trends_helper import fetch_comparable_interest

DB_PATH = "ml_trends.db"
GEO = "CL"
TIMEFRAME = "today 5-y"

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
        CREATE TABLE IF NOT EXISTS trends_google_history (
            date TEXT NOT NULL,
            category_name TEXT NOT NULL,
            keyword TEXT NOT NULL,
            interest_score INTEGER,
            PRIMARY KEY (date, category_name)
        )
        """
    )
    conn.commit()


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    pytrends = TrendReq(hl="es-CL", tz=240)
    keyword_to_category = {kw: name for name, kw in CATEGORY_KEYWORDS.items()}
    keywords = list(CATEGORY_KEYWORDS.values())

    df = fetch_comparable_interest(pytrends, keywords, GEO, TIMEFRAME)

    rows = []
    for keyword in keywords:
        category_name = keyword_to_category[keyword]
        for date, score in df[keyword].items():
            rows.append((date.isoformat(), category_name, keyword, int(round(score))))

    conn.executemany(
        """
        INSERT OR REPLACE INTO trends_google_history
            (date, category_name, keyword, interest_score)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    print(f"[OK] {len(rows)} puntos históricos guardados ({len(CATEGORY_KEYWORDS)} categorías x 5 años)")


if __name__ == "__main__":
    main()
