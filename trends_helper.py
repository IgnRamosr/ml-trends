"""
Helper para traer interés de Google Trends de más de 5 palabras clave a
la vez de forma COMPARABLE entre sí.

Google Trends normaliza cada consulta (máx. 5 keywords) de 0 a 100 de
forma independiente, así que si separas tus keywords en varios lotes,
los números de un lote NO son comparables con los de otro lote.

La solución es repetir una palabra "ancla" en todos los lotes y usar su
valor para reescalar los demás lotes al mismo punto de referencia.
"""

import time
from datetime import date

from pytrends.exceptions import TooManyRequestsError
from pytrends.request import TrendReq

MAX_RETRIES = 5
BASE_DELAY_SECONDS = 30


def _fetch_with_retry(pytrends: TrendReq, batch: list[str], geo: str, timeframe: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload(batch, geo=geo, timeframe=timeframe)
            return pytrends.interest_over_time()[batch]
        except TooManyRequestsError:
            if attempt == MAX_RETRIES:
                raise
            wait = BASE_DELAY_SECONDS * attempt
            print(f"  [429] Rate limited, reintentando en {wait}s (intento {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)


def fetch_comparable_interest(
    pytrends: TrendReq,
    keywords: list[str],
    geo: str,
    timeframe: str,
):
    """
    Devuelve un DataFrame con una columna por keyword, todas en la misma
    escala 0-100, sin importar cuántos lotes de 5 hicieron falta.
    """
    if len(keywords) <= 5:
        return _fetch_with_retry(pytrends, keywords, geo, timeframe)

    anchor = keywords[0]
    batches = []
    rest = keywords[1:]
    for i in range(0, len(rest), 4):
        batches.append([anchor] + rest[i : i + 4])

    combined = None
    base_anchor_series = None

    for batch in batches:
        df = _fetch_with_retry(pytrends, batch, geo, timeframe)
        time.sleep(5)  # espacio entre lotes para evitar 429

        if base_anchor_series is None:
            base_anchor_series = df[anchor]
            combined = df.copy()
            continue

        # Reescalar este lote para que su versión del ancla coincida con la base
        anchor_ratio = (base_anchor_series.mean() / df[anchor].mean()) if df[anchor].mean() else 1
        rescaled = df.drop(columns=[anchor]) * anchor_ratio
        combined = combined.join(rescaled)

    return combined


def fetch_rising_queries(pytrends: TrendReq, seed: str, geo: str, timeframe: str):
    """
    Devuelve el DataFrame de búsquedas relacionadas EN ALZA para una palabra
    semilla. Es la señal más cercana a "qué productos están ganando interés
    ahora" que existe gratis: no es una predicción de futuro, es una medida
    de crecimiento reciente de búsqueda relativa.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload([seed], geo=geo, timeframe=timeframe)
            related = pytrends.related_queries()
            return related[seed]["rising"]
        except TooManyRequestsError:
            if attempt == MAX_RETRIES:
                raise
            wait = BASE_DELAY_SECONDS * attempt
            print(f"  [429] Rate limited, reintentando en {wait}s (intento {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)


def fetch_region_interest(pytrends: TrendReq, seed: str, geo: str, timeframe: str):
    """Interés por región para una palabra, con reintentos automáticos por 429."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload([seed], geo=geo, timeframe=timeframe)
            return pytrends.interest_by_region(resolution="REGION", inc_low_vol=True)
        except TooManyRequestsError:
            if attempt == MAX_RETRIES:
                raise
            wait = BASE_DELAY_SECONDS * attempt
            print(f"  [429] Rate limited, reintentando en {wait}s (intento {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)


def analyze_word(pytrends: TrendReq, word: str, geo: str = "CL") -> dict:
    """
    Corre el análisis completo de una palabra: interés por región, fluctuación
    del año actual, comparativa con el mismo período del año pasado, y un
    veredicto basado en reglas simples (no es un modelo predictivo entrenado).

    Devuelve un dict con los dataframes crudos (para graficar si se quiere)
    y los campos resumidos (para tablas/comparación entre varias palabras).
    """
    today = date.today()
    today_str = today.isoformat()
    this_year_start = f"{today.year}-01-01"
    last_year_start = f"{today.year - 1}-01-01"
    last_year_end = f"{today.year - 1}-{today.month:02d}-{today.day:02d}"

    df_region = fetch_region_interest(pytrends, word, geo, "today 12-m")
    df_this_year = fetch_comparable_interest(pytrends, [word], geo, f"{this_year_start} {today_str}")
    df_last_year = fetch_comparable_interest(pytrends, [word], geo, f"{last_year_start} {last_year_end}")

    top_region_name = None
    top_region_value = 0
    if not df_region.empty and df_region[word].sum() > 0:
        region_sorted = df_region.sort_values(word, ascending=False)
        top_region_name = region_sorted.index[0]
        top_region_value = region_sorted.iloc[0][word]

    this_year_avg = 0
    trend_direction = "sin datos"
    if not df_this_year.empty:
        serie = df_this_year[word]
        this_year_avg = serie.mean()
        n = len(serie)
        quarter = max(1, n // 4)
        start_avg = serie.iloc[:quarter].mean()
        end_avg = serie.iloc[-quarter:].mean()
        if end_avg > start_avg * 1.15:
            trend_direction = "subiendo"
        elif end_avg < start_avg * 0.85:
            trend_direction = "bajando"
        else:
            trend_direction = "estable"

    last_year_avg = df_last_year[word].mean() if not df_last_year.empty else 0
    yoy_change = None
    if last_year_avg > 0:
        yoy_change = (this_year_avg - last_year_avg) / last_year_avg * 100

    points_favor = []
    points_contra = []

    if trend_direction == "subiendo":
        points_favor.append("el interés está subiendo dentro de este año")
    elif trend_direction == "bajando":
        points_contra.append("el interés está bajando dentro de este año")
    elif trend_direction == "estable":
        points_favor.append("el interés se mantiene estable este año")

    if yoy_change is not None:
        if yoy_change > 10:
            points_favor.append(f"creció un {yoy_change:.0f}% respecto al año pasado")
        elif yoy_change < -10:
            points_contra.append(f"cayó un {abs(yoy_change):.0f}% respecto al año pasado")

    if top_region_value >= 50:
        points_favor.append(f"zona fuerte: {top_region_name} ({top_region_value:.0f}/100)")
    elif top_region_name:
        points_contra.append("el interés más alto por región sigue siendo bajo")

    if len(points_favor) >= 2 and len(points_contra) == 0:
        verdict = "favorable"
    elif points_contra:
        verdict = "mixto"
    else:
        verdict = "insuficiente"

    return {
        "word": word,
        "df_region": df_region,
        "df_this_year": df_this_year,
        "df_last_year": df_last_year,
        "this_year_avg": this_year_avg,
        "last_year_avg": last_year_avg,
        "yoy_change": yoy_change,
        "trend_direction": trend_direction,
        "top_region_name": top_region_name,
        "top_region_value": top_region_value,
        "points_favor": points_favor,
        "points_contra": points_contra,
        "verdict": verdict,
    }


# Centroides aproximados (capital regional) para ubicar cada región de Chile
# en un mapa, ya que Google Trends solo da el nombre de la región, no coordenadas.
CHILE_REGION_COORDS = {
    "Región de Arica y Parinacota": (-18.48, -69.50),
    "Región de Tarapacá": (-20.21, -70.15),
    "III Región": (-27.37, -70.33),
    "Región de Antofagasta": (-23.65, -70.40),
    "Región de Coquimbo": (-29.95, -71.34),
    "Región de Valparaíso": (-33.05, -71.40),
    "Región Metropolitana": (-33.45, -70.65),
    "VI Región": (-34.57, -71.00),
    "VII Región": (-35.43, -71.66),
    "Región del Bío Bío": (-36.83, -73.05),
    "IX Región": (-38.74, -72.60),
    "Región de los Ríos": (-39.81, -73.25),
    "X Región": (-41.47, -72.94),
    "XI Región": (-45.57, -72.07),
    "Región de Magallanes y de la Antártica Chilena": (-53.16, -70.90),
}
