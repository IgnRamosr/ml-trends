"""
Corre el mismo análisis del dashboard (interés por región, fluctuación del
año, comparativa con el año pasado, veredicto) para una LISTA de palabras de
producto, agrupadas por categoría. Sirve para tantear varios candidatos a la
vez en vez de probarlos uno por uno en el dashboard.

Uso:
    python batch_analyze.py
    python batch_analyze.py --csv mi_lista.csv   # analiza un CSV propio

El CSV de entrada debe tener columnas: categoria,producto

Resultado: imprime una tabla en consola y la guarda en
batch_analysis_resultados.csv (se puede abrir en Excel).
"""

import sys
import time

import pandas as pd
from pytrends.request import TrendReq

from trends_helper import analyze_word

GEO = "CL"
DELAY_BETWEEN_WORDS_SECONDS = 8

PRODUCTS_BY_CATEGORY = {
    "Fitness y Suplementos": [
        "creatina",
        "proteina whey",
        "bcaa",
        "pre entreno",
        "colageno",
        "omega 3",
        "vitamina c",
        "multivitaminico",
        "caseina",
        "gainers",
        "glutamina",
        "quemador de grasa",
        "barra proteica",
        "mancuernas",
        "banda elastica",
        "colchoneta yoga",
        "soga de saltar",
        "guantes gimnasio",
        "rodillo foam",
        "cinturon gimnasio",
    ],
    "Tecnologia y Accesorios": [
        "audifonos bluetooth",
        "smartwatch",
        "powerbank",
        "camara web",
        "teclado mecanico",
        "mouse gaming",
        "soporte notebook",
        "hub usb",
        "parlante bluetooth",
        "lampara escritorio led",
        "anillo de luz",
        "disco duro externo",
        "memoria usb",
        "cargador inalambrico",
        "tripode celular",
        "drone",
    ],
    "Mascotas": [
        "cama para perro",
        "comedero automatico",
        "rascador para gatos",
        "collar led perro",
        "juguete para perro",
        "arena para gatos",
        "arnes para perro",
        "cortaunas mascotas",
        "cepillo para mascotas",
        "vitaminas para perros",
        "snacks para perro",
        "transportadora mascotas",
    ],
    "Hogar y Cocina": [
        "freidora de aire",
        "aspiradora robot",
        "purificador de aire",
        "cafetera",
        "licuadora portatil",
        "hervidor electrico",
        "sarten antiadherente",
        "organizador cocina",
        "lampara solar jardin",
    ],
    "Ropa y Calzado": [
        "zapatillas running",
        "mochila notebook",
        "calcetines deportivos",
        "poleron hombre",
        "gorro lana",
        "canguro deportivo",
    ],
}


def run_analysis(products_by_category: dict) -> pd.DataFrame:
    pytrends = TrendReq(hl="es-CL", tz=240)
    rows = []

    total = sum(len(v) for v in products_by_category.values())
    done = 0

    for category, words in products_by_category.items():
        for word in words:
            done += 1
            print(f"[{done}/{total}] Analizando '{word}' ({category})...")
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
                        "a_favor": "; ".join(result["points_favor"]),
                        "en_contra": "; ".join(result["points_contra"]),
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
                        "a_favor": "",
                        "en_contra": str(e),
                    }
                )
            time.sleep(DELAY_BETWEEN_WORDS_SECONDS)

    return pd.DataFrame(rows)


def main() -> None:
    # Si se pasa --csv archivo.csv, usa ese CSV como fuente
    if len(sys.argv) >= 3 and sys.argv[1] == "--csv":
        input_path = sys.argv[2]
        df_input = pd.read_csv(input_path)
        if not {"categoria", "producto"}.issubset(df_input.columns):
            print("ERROR: El CSV debe tener columnas 'categoria' y 'producto'")
            return
        products = {}
        for cat, group in df_input.groupby("categoria"):
            products[cat] = group["producto"].tolist()
    else:
        products = PRODUCTS_BY_CATEGORY

    df = run_analysis(products)
    df = df.sort_values(["categoria", "interes_este_anio"], ascending=[True, False])

    print("\n=== Resumen ===")
    print(df[["categoria", "producto", "interes_este_anio", "variacion_%", "tendencia", "veredicto"]].to_string(index=False))

    df.to_csv("batch_analysis_resultados.csv", index=False, encoding="utf-8-sig")
    print("\nGuardado en batch_analysis_resultados.csv")


if __name__ == "__main__":
    main()
