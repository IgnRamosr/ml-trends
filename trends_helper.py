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
