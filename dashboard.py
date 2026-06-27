"""
Dashboard simple con Streamlit para visualizar los snapshots
recolectados por fetch_trends.py y fetch_trends_google.py.

Correr con: streamlit run dashboard.py
"""

import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st
from pytrends.request import TrendReq

from trends_helper import fetch_comparable_interest

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
