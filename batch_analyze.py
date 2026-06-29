"""
Corre el mismo análisis del dashboard (interés por región, fluctuación del
año, comparativa con el año pasado, veredicto) para una LISTA de palabras de
producto, agrupadas por categoría. Sirve para tantear varios candidatos a la
vez en vez de probarlos uno por uno en el dashboard.

Uso:
    python batch_analyze.py

Edita PRODUCTS_BY_CATEGORY más abajo para cambiar qué se analiza. Las
palabras pueden ser generales (ej. "creatina", "freidora de aire") en vez
de un producto específico con marca/modelo/gramaje.

Resultado: imprime una tabla en consola y la guarda en
batch_analysis_resultados.csv (se puede abrir en Excel).
"""

import time

import pandas as pd
from pytrends.request import TrendReq

from trends_helper import analyze_word

GEO = "CL"
DELAY_BETWEEN_WORDS_SECONDS = 8  # evitar 429 al encadenar muchas palabras

# Editar libremente: categoría -> lista de palabras generales a tantear.
PRODUCTS_BY_CATEGORY = {
    "Fitness y Suplementos": ["creatina", "proteina whey", "mancuernas", "banda elastica"],
    "Hogar y Cocina": ["freidora de aire", "aspiradora robot", "purificador de aire"],
    "Tecnologia y Accesorios": ["audifonos bluetooth", "smartwatch", "powerbank", "drone"],
    "Ropa y Calzado": ["zapatillas running", "polerón oversize", "mochila notebook"],
}


def main() -> None:
    pytrends = TrendReq(hl="es-CL", tz=240)
    rows = []

    for category, words in PRODUCTS_BY_CATEGORY.items():
        for word in words:
            print(f"Analizando '{word}' ({category})...")
            try:
                result = analyze_word(pytrends, word, geo=GEO)
                rows.append(
                    {
                        "categoria": category,
                        "producto": word,
                        "interes_este_anio": round(result["this_year_avg"]),
                        "interes_anio_pasado": round(result["last_year_avg"]),
                        "variacion_%": round(result["yoy_change"]) if result["yoy_change"] is not None else None,
                        "tendencia": result["trend_direction"],
                        "zona_top": result["top_region_name"],
                        "interes_zona_top": round(result["top_region_value"]),
                        "veredicto": result["verdict"],
                    }
                )
                print(f"  -> veredicto: {result['verdict']}")
            except Exception as e:
                print(f"  [ERROR] {word}: {e}")
                rows.append(
                    {
                        "categoria": category,
                        "producto": word,
                        "interes_este_anio": None,
                        "interes_anio_pasado": None,
                        "variacion_%": None,
                        "tendencia": None,
                        "zona_top": None,
                        "interes_zona_top": None,
                        "veredicto": "error",
                    }
                )
            time.sleep(DELAY_BETWEEN_WORDS_SECONDS)

    df = pd.DataFrame(rows)
    df = df.sort_values(["categoria", "interes_este_anio"], ascending=[True, False])

    print("\n=== Resumen ===")
    print(df.to_string(index=False))

    df.to_csv("batch_analysis_resultados.csv", index=False, encoding="utf-8-sig")
    print("\nGuardado en batch_analysis_resultados.csv")


if __name__ == "__main__":
    main()
