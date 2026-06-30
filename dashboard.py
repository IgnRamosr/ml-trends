"""
Dashboard simple con Streamlit para visualizar los snapshots
recolectados por fetch_trends.py y fetch_trends_google.py.

Correr con: streamlit run dashboard.py
"""

import sqlite3
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from pytrends.request import TrendReq

from trends_helper import (
    CHILE_REGION_COORDS,
    analyze_word,
    fetch_comparable_interest,
    fetch_region_interest,
    fetch_rising_queries,
)

DB_PATH = "ml_trends.db"

st.set_page_config(page_title="Mercado Libre - Best Sellers", layout="wide")
st.title("Qué productos conviene revender — Chile")

PLOTLY_TEMPLATE = "plotly_dark"
COLOR_SEQUENCE = px.colors.qualitative.Vivid


@st.cache_data(ttl=300)
def load_ml_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM snapshots", conn)
    conn.close()
    if not df.empty:
        df["captured_at"] = pd.to_datetime(df["captured_at"])
    return df


@st.cache_data(ttl=300)
def load_trends_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM trends_google", conn)
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    conn.close()
    if not df.empty:
        df["captured_at"] = pd.to_datetime(df["captured_at"])
    return df


@st.cache_data(ttl=300)
def load_trends_history() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM trends_google_history", conn)
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        # Eje numérico (no texto) para que line_shape="spline" funcione bien y
        # para poder superponer años usando el mismo día-del-año como referencia.
        # Restamos el offset de año bisiesto para que el 1 de marzo caiga en el
        # mismo punto todos los años (aproximación suficiente para esta vista).
        is_leap = df["date"].dt.is_leap_year
        day_of_year = df["date"].dt.dayofyear
        df["day_of_year_num"] = day_of_year - ((day_of_year > 59) & is_leap).astype(int)
    return df


ml_df = load_ml_data()
trends_df = load_trends_data()
trends_history_df = load_trends_history()

if ml_df.empty:
    st.warning("Todavía no hay datos. Corre `python fetch_trends.py` primero.")
    st.stop()

_SECCIONES_ANTERIORES_DESHABILITADAS = """

# --- Sección 0: recomendación rápida (cruce de todas las señales) ---
st.header("0. Qué publicar primero en Facebook Marketplace")
st.caption(
    "Cruce directo de las dos señales reales que tenemos: categorías con más demanda "
    "(Google Trends) y, dentro de cada una, el producto que REALMENTE más vende en "
    "Mercado Libre (no estimado, es su ranking real). Esto no es una garantía de venta "
    "en Facebook Marketplace — es el punto de partida más informado que podemos darte "
    "con fuentes gratuitas. Antes de invertir en stock, valida con la Sección 6 si hay "
    "una marca/modelo específico en alza dentro de este producto, y con la Sección 3 que "
    "el interés sea sostenido y no un pico de un solo día."
)

if not trends_df.empty:
    demand_by_category = (
        trends_df.sort_values("captured_at")
        .groupby("category_name", as_index=False)
        .last()[["category_name", "interest_score"]]
        .rename(columns={"interest_score": "demanda"})
    )

    top1_by_category = (
        ml_df.sort_values("captured_at")
        .groupby("product_id", as_index=False)
        .last()
        .sort_values(["category_name", "position"])
        .groupby("category_name", as_index=False)
        .first()[["category_name", "title", "price", "permalink"]]
    )

    recommendation = demand_by_category.merge(top1_by_category, on="category_name", how="left")
    recommendation = recommendation.sort_values("demanda", ascending=False)

    for _, row in recommendation.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            c1.metric(row["category_name"], f"{row['demanda']}/100 demanda")
            if pd.notna(row["title"]):
                c2.markdown(f"**Producto top en ML:** {row['title']}")
                c2.markdown(f"${row['price']:,.0f} · [Ver en Mercado Libre]({row['permalink']})")
            else:
                c2.markdown("_Sin producto registrado en ML para esta categoría todavía._")
else:
    st.info("Corre `python fetch_trends_google.py` para ver esta recomendación.")

st.divider()

# --- Sección 1: comparación de demanda entre categorías (Google Trends) ---
st.header("1. Qué categoría tiene más demanda")
st.caption(
    "Interés de búsqueda promedio en Google (últimos 12 meses, Chile). "
    "Mercado Libre no permite comparar volumen de venta entre categorías "
    "en su API gratuita, así que usamos esta señal externa para esa comparación."
)

if trends_df.empty:
    st.info("Corre `python fetch_trends_google.py` para ver esta sección.")
else:
    latest_trends = (
        trends_df.sort_values("captured_at")
        .groupby("category_name", as_index=False)
        .last()
        .sort_values("interest_score", ascending=True)
    )
    fig_trends = px.bar(
        latest_trends,
        x="interest_score",
        y="category_name",
        orientation="h",
        text="interest_score",
        color="category_name",
        color_discrete_sequence=COLOR_SEQUENCE,
        template=PLOTLY_TEMPLATE,
    )
    fig_trends.update_layout(
        showlegend=False,
        xaxis_title="Interés de búsqueda (0-100)",
        yaxis_title="",
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig_trends.update_traces(textposition="outside")
    st.plotly_chart(fig_trends, width='stretch')

st.divider()

# --- Sección 2: productos ganadores dentro de cada categoría ---
st.header("2. Qué producto específico conviene revender")
st.caption(
    "Top 3 más vendidos por categoría según Mercado Libre (posición 1 = el más vendido "
    "de TODA la categoría, no solo de esta lista — es la señal más fuerte que tenemos)."
)

categories = sorted(ml_df["category_name"].unique())
selected_category = st.selectbox("Filtrar por categoría", ["Todas"] + categories)
filtered = ml_df if selected_category == "Todas" else ml_df[ml_df["category_name"] == selected_category]

latest = (
    filtered.sort_values("captured_at")
    .groupby("product_id", as_index=False)
    .last()
)

top3 = (
    latest.sort_values(["category_name", "position"])
    .groupby("category_name", as_index=False)
    .head(3)
)

fig_top3 = px.bar(
    top3.sort_values("position", ascending=False),
    x="position",
    y="title",
    color="category_name",
    orientation="h",
    text="price",
    color_discrete_sequence=COLOR_SEQUENCE,
    template=PLOTLY_TEMPLATE,
    hover_data={"price": ":,.0f", "permalink": True},
)
fig_top3.update_layout(
    xaxis_title="Posición en el ranking (1 = más vendido)",
    yaxis_title="",
    legend_title="Categoría",
    margin=dict(l=10, r=10, t=10, b=10),
    height=120 + 40 * len(top3),
)
fig_top3.update_xaxes(autorange="reversed")
fig_top3.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
st.plotly_chart(fig_top3, width='stretch')

with st.expander("Ver tabla completa con links a Mercado Libre"):
    table = latest.sort_values(["category_name", "position"])
    st.dataframe(
        table[["category_name", "position", "title", "price", "condition", "permalink"]],
        width='stretch',
        hide_index=True,
    )

st.divider()

# --- Sección 3: búsqueda libre de interés en Google Trends ---
st.header("3. Interés de búsqueda de una palabra específica")
st.caption(
    "Escribe cualquier palabra o producto y consulta su interés de búsqueda real "
    "en Google (Chile, últimos 12 meses). Sirve para validar una idea puntual "
    "sin esperar a que el histórico de Mercado Libre se acumule con el tiempo."
)

search_word = st.text_input("Palabra a buscar", placeholder="ej. creatina, freidora de aire, zapatillas nike")

if search_word and st.button("Buscar interés"):
    with st.spinner(f"Consultando Google Trends para '{search_word}'..."):
        try:
            pytrends = TrendReq(hl="es-CL", tz=240)
            pytrends.build_payload([search_word], geo="CL", timeframe="today 12-m")
            df_word = pytrends.interest_over_time()

            if df_word.empty:
                st.warning("Google Trends no devolvió datos para esa palabra (puede ser muy poco buscada).")
            else:
                serie = df_word[search_word]
                max_val = serie.max()
                min_val = serie.min()
                max_dates = df_word.index[serie == max_val].strftime("%d-%m-%Y").tolist()
                min_dates = df_word.index[serie == min_val].strftime("%d-%m-%Y").tolist()

                col1, col2, col3 = st.columns(3)
                col1.metric("Interés máximo", f"{max_val}/100")
                col1.caption("Fecha(s): " + ", ".join(max_dates))
                col2.metric("Interés mínimo", f"{min_val}/100")
                col2.caption("Fecha(s): " + ", ".join(min_dates))
                col3.metric("Promedio 12 meses", f"{serie.mean():.0f}/100")

                fig_word = px.line(
                    df_word.reset_index(),
                    x="date",
                    y=search_word,
                    markers=True,
                    template=PLOTLY_TEMPLATE,
                    color_discrete_sequence=COLOR_SEQUENCE,
                    line_shape="spline",
                )
                fig_word.update_yaxes(title="Interés de búsqueda (0-100)", range=[0, 100])
                fig_word.update_xaxes(title="Fecha")
                fig_word.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_word, width='stretch')
        except Exception as e:
            st.error(f"No se pudo consultar Google Trends: {e}")

st.divider()

# --- Sección 4: comparativa de demanda por año (Google Trends) ---
st.header("4. Comparativa por año (estacionalidad)")
st.caption(
    "Interés de búsqueda en Google superpuesto por año, para una misma categoría. "
    "Sirve para detectar patrones que se repiten cada año (ej. picos en diciembre)."
)

if trends_history_df.empty:
    st.info("Corre `python fetch_trends_google_history.py` para ver esta sección.")
else:
    history_categories = sorted(trends_history_df["category_name"].unique())
    selected_history_category = st.selectbox(
        "Elegir categoría", history_categories, key="history_category"
    )
    cat_history = trends_history_df[
        trends_history_df["category_name"] == selected_history_category
    ].sort_values(["year", "day_of_year_num"])
    cat_history = cat_history.astype({"year": str})

    fig_year = px.line(
        cat_history,
        x="day_of_year_num",
        y="interest_score",
        color="year",
        markers=False,
        template=PLOTLY_TEMPLATE,
        color_discrete_sequence=COLOR_SEQUENCE,
        line_shape="spline",
    )
    fig_year.update_traces(line=dict(width=2.5))
    # Día 1 de cada mes en un año no bisiesto, para ubicar las etiquetas Ene..Dic
    month_starts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    fig_year.update_xaxes(
        title="Mes",
        tickmode="array",
        tickvals=month_starts,
        ticktext=[
            "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
        ],
    )
    fig_year.update_yaxes(title="Interés de búsqueda (0-100)")
    fig_year.update_layout(legend_title="Año", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_year, width='stretch')

st.divider()

# --- Sección 5: cruce de productos ML con interés de búsqueda en Google ---
st.header("5. Cuál producto específico tiene más interés de búsqueda")
st.caption(
    "Toma productos top de Mercado Libre y consulta su interés real en Google Trends. "
    "Útil para desempatar entre varios productos top: el que más se BUSCA además de venderse "
    "bien es candidato más seguro para revender. Máximo 5 productos por consulta "
    "(límite de Google Trends)."
)


def shorten_title(title: str, words: int = 4) -> str:
    return " ".join(title.split()[:words])


latest_all = (
    ml_df.sort_values("captured_at")
    .groupby("product_id", as_index=False)
    .last()
    .sort_values(["category_name", "position"])
)

product_options = latest_all["title"].dropna().unique().tolist()
selected_products = st.multiselect(
    "Elegir hasta 5 productos para comparar",
    product_options,
    default=product_options[:3] if len(product_options) >= 3 else product_options,
    max_selections=5,
)

if selected_products and st.button("Comparar en Google Trends"):
    with st.spinner("Consultando Google Trends..."):
        short_labels = [shorten_title(t) for t in selected_products]
        pytrends = TrendReq(hl="es-CL", tz=240)
        try:
            df_products = fetch_comparable_interest(pytrends, short_labels, "CL", "today 3-m")
            avg_scores = df_products[short_labels].mean().reset_index()
            avg_scores.columns = ["producto", "interes"]
            avg_scores = avg_scores.sort_values("interes", ascending=True)

            fig_products = px.bar(
                avg_scores,
                x="interes",
                y="producto",
                orientation="h",
                text="interes",
                color="producto",
                color_discrete_sequence=COLOR_SEQUENCE,
                template=PLOTLY_TEMPLATE,
            )
            fig_products.update_layout(
                showlegend=False,
                xaxis_title="Interés de búsqueda (0-100)",
                yaxis_title="",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig_products.update_traces(textposition="outside")
            st.plotly_chart(fig_products, width='stretch')
            st.caption(
                "Nota: usamos una versión acortada del título (primeras 4 palabras) porque "
                "los títulos completos de Mercado Libre son demasiado específicos para tener "
                "volumen de búsqueda medible en Google."
            )
        except Exception as e:
            st.error(f"No se pudo consultar Google Trends: {e}")

st.divider()

# --- Sección 6: productos/marcas en alza por categoría ---
st.header("6. Qué productos están ganando interés ahora")
st.caption(
    "Búsquedas relacionadas EN ALZA para una palabra semilla (los últimos 3 meses, Chile). "
    "Esto NO es una predicción del futuro — es la señal más cercana que existe gratis a "
    "'qué está empezando a moverse ahora', basada en crecimiento real de búsquedas. "
    "Usa una palabra de PRODUCTO (ej. 'zapatillas', 'audifonos', 'freidora'), no una "
    "categoría genérica (ej. 'deportes' mezcla resultados de fútbol en Chile)."
)

seed_word = st.text_input(
    "Palabra semilla (producto, no categoría genérica)",
    placeholder="ej. zapatillas, audifonos bluetooth, freidora de aire",
    key="seed_word",
)

if seed_word and st.button("Ver productos en alza"):
    with st.spinner(f"Consultando búsquedas en alza para '{seed_word}'..."):
        try:
            pytrends = TrendReq(hl="es-CL", tz=240)
            rising = fetch_rising_queries(pytrends, seed_word, "CL", "today 3-m")

            if rising is None or rising.empty:
                st.warning(
                    "Google Trends no encontró búsquedas relacionadas en alza para esa palabra "
                    "(puede ser muy específica o tener poco volumen)."
                )
            else:
                rising = rising.rename(columns={"query": "Búsqueda relacionada", "value": "Crecimiento"})
                st.dataframe(rising, width="stretch", hide_index=True)
                st.caption(
                    "'Crecimiento' es un valor relativo de Google (no porcentaje exacto comparable "
                    "entre palabras distintas) — entre más alto, más rápido está creciendo esa "
                    "búsqueda específica en los últimos 3 meses."
                )
        except Exception as e:
            st.error(f"No se pudo consultar Google Trends: {e}")

st.divider()

# --- Sección 7: mapa de calor por región (Google Trends) ---
st.header("7. Dónde se busca más una palabra (mapa de Chile)")
st.caption(
    "Distribución del interés de búsqueda por región, últimos 12 meses. "
    "Usamos las capitales regionales como referencia geográfica (Google Trends no "
    "da coordenadas exactas, solo el nombre de la región), así que el tamaño/color "
    "de cada punto representa el interés relativo de toda la región, no un barrio "
    "o ciudad específica."
)

map_word = st.text_input(
    "Palabra a mapear", placeholder="ej. zapatillas, freidora de aire", key="map_word"
)

if map_word and st.button("Ver mapa de calor"):
    with st.spinner(f"Consultando interés por región para '{map_word}'..."):
        try:
            pytrends = TrendReq(hl="es-CL", tz=240)
            pytrends.build_payload([map_word], geo="CL", timeframe="today 12-m")
            df_region = pytrends.interest_by_region(resolution="REGION", inc_low_vol=True)

            if df_region.empty or df_region[map_word].sum() == 0:
                st.warning("Google Trends no devolvió datos por región para esa palabra.")
            else:
                df_region = df_region.reset_index()
                df_region["lat"] = df_region["geoName"].map(lambda r: CHILE_REGION_COORDS.get(r, (None, None))[0])
                df_region["lon"] = df_region["geoName"].map(lambda r: CHILE_REGION_COORDS.get(r, (None, None))[1])
                df_region = df_region.dropna(subset=["lat", "lon"])

                fig_map = px.scatter_geo(
                    df_region,
                    lat="lat",
                    lon="lon",
                    size=map_word,
                    color=map_word,
                    hover_name="geoName",
                    color_continuous_scale="Inferno",
                    template=PLOTLY_TEMPLATE,
                    scope="south america",
                    size_max=40,
                )
                fig_map.update_geos(
                    center=dict(lat=-35, lon=-71),
                    projection_scale=4,
                    showcountries=True,
                    countrycolor="gray",
                )
                fig_map.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_map, width="stretch")

                with st.expander("Ver tabla completa por región"):
                    st.dataframe(
                        df_region[["geoName", map_word]].sort_values(map_word, ascending=False),
                        width="stretch",
                        hide_index=True,
                    )
        except Exception as e:
            st.error(f"No se pudo consultar Google Trends: {e}")

"""

# =========================================================================
# Análisis único: ¿conviene publicar este producto en Facebook Marketplace?
# =========================================================================
st.title("¿Conviene publicar este producto en Facebook Marketplace?")
st.caption(
    "Escribe una palabra de PRODUCTO (no categoría genérica) y se analiza: "
    "en qué zonas hay más interés, cómo ha fluctuado este año, y cómo se compara "
    "con el mismo período del año pasado. Al final se entrega una conclusión. "
    "Recuerda: esto mide interés de búsqueda, no ventas confirmadas. La recomendación "
    "final es publicar el producto en Facebook Marketplace sin tener stock todavía, "
    "solo para medir la interacción real (vistas, mensajes) antes de invertir en comprarlo."
)

analysis_word = st.text_input(
    "Palabra de producto a analizar",
    placeholder="ej. zapatillas nike, freidora de aire, audifonos bluetooth",
    key="analysis_word",
)

if analysis_word and st.button("Analizar"):
    today = date.today()

    with st.spinner(f"Analizando '{analysis_word}'..."):
        try:
            pytrends = TrendReq(hl="es-CL", tz=240)
            result = analyze_word(pytrends, analysis_word, geo="CL")

            st.success("Análisis completo")

            st.subheader("1. Zonas con mayor interés")
            df_region = result["df_region"]
            if df_region.empty or df_region[analysis_word].sum() == 0:
                st.info("Sin suficiente volumen para desglosar por región.")
            else:
                df_region = df_region.reset_index()
                df_region["lat"] = df_region["geoName"].map(lambda r: CHILE_REGION_COORDS.get(r, (None, None))[0])
                df_region["lon"] = df_region["geoName"].map(lambda r: CHILE_REGION_COORDS.get(r, (None, None))[1])
                df_region_plot = df_region.dropna(subset=["lat", "lon"])

                fig_map = px.scatter_geo(
                    df_region_plot,
                    lat="lat",
                    lon="lon",
                    size=analysis_word,
                    color=analysis_word,
                    hover_name="geoName",
                    color_continuous_scale="Inferno",
                    template=PLOTLY_TEMPLATE,
                    scope="south america",
                    size_max=40,
                )
                fig_map.update_geos(
                    center=dict(lat=-35, lon=-71),
                    projection_scale=4,
                    showcountries=True,
                    countrycolor="gray",
                )
                fig_map.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_map, width="stretch")

            st.divider()

            st.subheader(f"2. Fluctuación durante {today.year}")
            df_this_year = result["df_this_year"]
            if df_this_year.empty:
                st.info("Sin datos suficientes para este año.")
            else:
                fig_this_year = px.line(
                    df_this_year.reset_index(),
                    x="date",
                    y=analysis_word,
                    markers=True,
                    template=PLOTLY_TEMPLATE,
                    color_discrete_sequence=COLOR_SEQUENCE,
                    line_shape="spline",
                )
                fig_this_year.update_yaxes(title="Interés de búsqueda (0-100)", range=[0, 100])
                fig_this_year.update_xaxes(title="Fecha")
                fig_this_year.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_this_year, width="stretch")

            st.divider()

            st.subheader(f"3. {today.year} vs {today.year - 1} (mismo período: 1-ene a hoy)")
            col1, col2, col3 = st.columns(3)
            col1.metric(f"Promedio {today.year}", f"{result['this_year_avg']:.0f}/100")
            col2.metric(f"Promedio {today.year - 1}", f"{result['last_year_avg']:.0f}/100")
            if result["yoy_change"] is not None:
                col3.metric("Variación año contra año", f"{result['yoy_change']:+.0f}%")
            else:
                col3.metric("Variación año contra año", "sin base")

            st.divider()

            st.subheader("4. Conclusión")
            points_favor = result["points_favor"]
            points_contra = result["points_contra"]

            if result["verdict"] == "favorable":
                st.success(
                    "Sí parece un buen candidato para probar este mes. A favor: "
                    + "; ".join(points_favor) + "."
                )
            elif result["verdict"] == "mixto":
                a_favor_txt = "; ".join(points_favor) if points_favor else "ninguna señal fuerte"
                st.warning(
                    "Señales mixtas o débiles, no es un candidato claro ahora. A favor: "
                    + a_favor_txt + ". En contra: " + "; ".join(points_contra) + "."
                )
            else:
                st.info("Señales insuficientes para concluir con confianza, datos muy bajos en volumen.")

            st.caption(
                "Esto no es garantía de venta, es interés de búsqueda. El siguiente paso recomendado "
                "es publicar este producto en Facebook Marketplace sin comprar stock todavía, y "
                "medir cuántas vistas o mensajes recibe en 1-2 semanas antes de invertir en comprarlo."
            )

        except Exception as e:
            st.error(f"No se pudo completar el análisis: {e}")

st.divider()

# =========================================================================
# Análisis por lote: subir CSV y obtener veredicto para varios productos
# =========================================================================
st.header("Análisis por lote — subir tu lista de productos")
st.caption(
    "Sube un CSV con columnas 'categoria' y 'producto'. Se analizan TODOS los productos "
    "sin límite: la tabla se actualiza en vivo después de cada uno manteniendo la conexión "
    "activa aunque tarde 20-30 minutos. Cada resultado se guarda a disco inmediatamente "
    "— si algo falla a mitad puedes reanudar desde donde quedó sin re-analizar todo."
)

with open("productos_template.csv", "rb") as f:
    st.download_button(
        label="Descargar plantilla CSV de ejemplo (63 productos)",
        data=f,
        file_name="productos_template.csv",
        mime="text/csv",
    )

uploaded_file = st.file_uploader(
    "Sube tu CSV de productos (columnas: categoria, producto)",
    type=["csv"],
    key="batch_upload",
)

CHECKPOINT_PATH = "batch_checkpoint.csv"

if uploaded_file is not None:
    import hashlib
    import time as _time

    raw_bytes = uploaded_file.read()
    file_hash = hashlib.md5(raw_bytes).hexdigest()[:8]
    df_input = pd.read_csv(pd.io.common.BytesIO(raw_bytes)).reset_index(drop=True)

    if not {"categoria", "producto"}.issubset(df_input.columns):
        st.error("El CSV debe tener columnas 'categoria' y 'producto'.")
    else:
        st.write(f"**{len(df_input)} productos cargados:**")
        st.dataframe(df_input, width="stretch", hide_index=True)

        # Cargar checkpoint de una corrida anterior del mismo archivo
        already_done = []
        try:
            ck = pd.read_csv(CHECKPOINT_PATH)
            if "_file_hash" in ck.columns and str(ck["_file_hash"].iloc[0]) == file_hash:
                already_done = ck.drop(columns=["_file_hash"]).to_dict("records")
        except Exception:
            pass

        done_products = {r["producto"] for r in already_done}
        pending = df_input[~df_input["producto"].isin(done_products)]

        if already_done:
            st.info(
                f"Análisis previo encontrado: {len(already_done)}/{len(df_input)} productos "
                "ya listos. Puedes reanudar o empezar desde cero."
            )
            col_a, col_b = st.columns(2)
            do_resume = col_a.button("Reanudar", key="batch_resume")
            do_restart = col_b.button("Empezar desde cero", key="batch_restart")
        else:
            do_resume = st.button("Analizar todos", key="batch_run")
            do_restart = False

        if do_restart:
            already_done = []
            pending = df_input
            try:
                import os; os.remove(CHECKPOINT_PATH)
            except Exception:
                pass

        if do_resume or do_restart:
            results = list(already_done)
            pytrends = TrendReq(hl="es-CL", tz=240)
            progress_bar = st.progress(
                len(results) / len(df_input),
                text=f"Completados {len(results)}/{len(df_input)}",
            )
            table_slot = st.empty()
            dl_slot = st.empty()

            def _render(rows):
                if not rows:
                    return
                df_r = pd.DataFrame(rows).sort_values(
                    ["veredicto", "interes_este_anio"], ascending=[True, False]
                )
                fav = df_r[df_r["veredicto"] == "favorable"]["producto"].tolist()
                if fav:
                    table_slot.success(
                        f"{len(fav)} candidatos favorables hasta ahora: " + ", ".join(fav)
                    )
                table_slot.dataframe(df_r, width="stretch", hide_index=True)
                dl_slot.download_button(
                    label=f"Descargar resultados parciales ({len(rows)} productos)",
                    data=df_r.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name="batch_resultados.csv",
                    mime="text/csv",
                    key=f"dl_{len(rows)}",
                )

            _render(results)

            for _, row in pending.iterrows():
                word = str(row["producto"])
                cat = str(row["categoria"])
                progress_bar.progress(
                    len(results) / len(df_input),
                    text=f"[{len(results)+1}/{len(df_input)}] Analizando '{word}'...",
                )
                try:
                    res = analyze_word(pytrends, word, geo="CL")
                    results.append({
                        "categoria": cat,
                        "producto": word,
                        "interes_este_anio": round(res["this_year_avg"]),
                        "interes_anio_pasado": round(res["last_year_avg"]),
                        "variacion_%": f"{res['yoy_change']:+.0f}%" if res["yoy_change"] is not None else "sin base",
                        "tendencia": res["trend_direction"],
                        "zona_top": res["top_region_name"],
                        "veredicto": res["verdict"],
                        "a_favor": "; ".join(res["points_favor"]),
                        "en_contra": "; ".join(res["points_contra"]),
                    })
                except Exception as e:
                    results.append({
                        "categoria": cat,
                        "producto": word,
                        "interes_este_anio": None,
                        "interes_anio_pasado": None,
                        "variacion_%": None,
                        "tendencia": None,
                        "zona_top": None,
                        "veredicto": "error",
                        "a_favor": "",
                        "en_contra": str(e),
                    })

                # Guardar checkpoint después de cada producto
                ck_df = pd.DataFrame(results)
                ck_df["_file_hash"] = file_hash
                ck_df.to_csv(CHECKPOINT_PATH, index=False, encoding="utf-8-sig")

                _render(results)
                _time.sleep(8)

            progress_bar.progress(1.0, text=f"Completado — {len(results)} productos analizados.")
            st.balloons()
