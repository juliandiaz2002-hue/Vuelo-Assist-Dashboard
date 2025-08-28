# app.py
# Dashboard de reclamos (Excel) — listo para Streamlit/Cloud
# Requisitos: streamlit, pandas, plotly, openpyxl

import io
import os
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Dashboard de Reclamos", layout="wide")
st.title("📊 Dashboard de Reclamos de Aerolíneas")

st.markdown(
    "Sube tu archivo **Excel** (.xlsx) con columnas como: `nid`, `fecha`, `categoria`, `aerolinea`, `origen`, `destino`, `titulo`, `url`, etc."
)

DEFAULT_XLSX = "Con_mas_info_recategorized.xlsx"

file = st.file_uploader("Subir Excel .xlsx", type=["xlsx"])

@st.cache_data
def load_df(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0)
    # Normalizaciones mínimas
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    # Estándar de nombres esperados
    rename_map = {c: c.strip().lower() for c in df.columns}
    df.columns = list(rename_map.values())
    # Campos faltantes que usaremos
    for col in ["categoria", "aerolinea", "origen", "destino"]:
        if col not in df.columns:
            df[col] = None
    return df

# -------- CARGA DE DATOS (uploader o archivo del repo) --------
df = None
if file is not None:
    df = load_df(file.read())
elif os.path.exists(DEFAULT_XLSX):
    st.success(f"Usando el archivo incluido en el repositorio: **{DEFAULT_XLSX}**")
    with open(DEFAULT_XLSX, "rb") as f:
        df = load_df(f.read())

# Función para crear esquema de colores personalizado
def get_custom_colors(categories):
    """Crea un esquema de colores personalizado destacando categorías importantes"""
    important_colors = {
        "cancelación": "#FF6B6B",
        "overbooking": "#4ECDC4",
        "retraso": "#45B7D1",
        "perdida o daño de maleta": "#96CEB4"
    }
    default_color = "#E0E0E0"
    color_map = {}
    for cat in categories:
        cat_lower = str(cat).lower().strip()
        color_map[cat] = important_colors.get(cat_lower, default_color)
    return color_map

# -------- DASHBOARD --------
if df is not None:

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        aerolinea_sel = st.multiselect("Aerolínea", sorted([x for x in df["aerolinea"].dropna().unique()]))
    with col2:
        categoria_sel = st.multiselect("Categoría", sorted([x for x in df["categoria"].dropna().unique()]))
    with col3:
        if "fecha" in df.columns and pd.api.types.is_datetime64_any_dtype(df["fecha"]):
            min_d, max_d = df["fecha"].min(), df["fecha"].max()
            rango = st.date_input("Rango de fechas", value=(
                min_d.date() if pd.notnull(min_d) else None,
                max_d.date() if pd.notnull(max_d) else None
            ))
        else:
            rango = None

    df_f = df.copy()
    if aerolinea_sel:
        df_f = df_f[df_f["aerolinea"].isin(aerolinea_sel)]
    if categoria_sel:
        df_f = df_f[df_f["categoria"].isin(categoria_sel)]
    if rango and isinstance(rango, tuple) and len(rango) == 2 and all(rango):
        d0, d1 = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
        if "fecha" in df_f.columns and pd.api.types.is_datetime64_any_dtype(df_f["fecha"]):
            df_f = df_f[(df_f["fecha"] >= d0) & (df_f["fecha"] <= d1)]

    # Derivados
    if "fecha" in df_f.columns and pd.api.types.is_datetime64_any_dtype(df_f["fecha"]):
        dow_map = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        df_f["dia_semana"] = df_f["fecha"].dt.day_name().map(dow_map)
        df_f["anio_mes"] = df_f["fecha"].dt.to_period("M").astype(str)

    # KPIs
    total = len(df_f)
    cats = df_f["categoria"].nunique(dropna=True)
    airlines = df_f["aerolinea"].nunique(dropna=True)
    colA, colB, colC = st.columns(3)
    colA.metric("Reclamos (filtrados)", f"{total}")
    colB.metric("Categorías", f"{cats}")
    colC.metric("Aerolíneas", f"{airlines}")

    # Gráficos principales
    st.subheader("Distribuciones principales")
    c1, c2 = st.columns(2)
    with c1:
        if df_f["categoria"].notna().any():
            cat_counts = df_f.groupby("categoria").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False)
            custom_colors = get_custom_colors(cat_counts["categoria"].tolist())
            fig = px.bar(
                cat_counts,
                x="categoria", y="reclamos",
                title="Reclamos por categoría",
                color="categoria", color_discrete_map=custom_colors
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if df_f["aerolinea"].notna().any():
            fig = px.bar(
                df_f.groupby("aerolinea").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False),
                x="aerolinea", y="reclamos", title="Reclamos por aerolínea"
            )
            st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        if "dia_semana" in df_f.columns and df_f["dia_semana"].notna().any():
            order_dow = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
            fig = px.bar(
                df_f.groupby("dia_semana").size().reindex(order_dow).reset_index(name="reclamos").dropna(),
                x="dia_semana", y="reclamos", title="Reclamos por día de la semana"
            )
            st.plotly_chart(fig, use_container_width=True)
    with c4:
        if df_f[["origen","destino"]].notna().any(axis=None):
            rutas = (
                df_f.groupby(["origen","destino"]).size().reset_index(name="reclamos")
                .sort_values("reclamos", ascending=False).head(15)
            )
            rutas["ruta"] = rutas["origen"].fillna("?") + " → " + rutas["destino"].fillna("?")
            fig = px.bar(rutas, x="reclamos", y="ruta", orientation="h", title="Top rutas con más reclamos (Top 15)")
            st.plotly_chart(fig, use_container_width=True)

    # Tendencia temporal
    st.subheader("Tendencia temporal")
    if "anio_mes" in df_f.columns:
        serie = df_f.groupby("anio_mes").size().reset_index(name="reclamos")
        fig = px.line(serie, x="anio_mes", y="reclamos", markers=True, title="Reclamos por mes")
        st.plotly_chart(fig, use_container_width=True)

    # Gráfico de categorías con colores destacados
    st.subheader("📊 Categorías destacadas")
    if df_f["categoria"].notna().any():
        cat_counts = df_f.groupby("categoria").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False)
        custom_colors = get_custom_colors(cat_counts["categoria"].tolist())
        fig = px.bar(
            cat_counts,
            x="reclamos", y="categoria",
            orientation="h",
            title="Reclamos por categoría (categorías importantes destacadas)",
            color="categoria", color_discrete_map=custom_colors
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**🎨 Categorías destacadas:**")
        important_cats = ["Cancelación", "Overbooking", "Retraso", "Perdida o daño de maleta"]
        for cat in important_cats:
            if cat in cat_counts["categoria"].values:
                count = cat_counts[cat_counts["categoria"] == cat]["reclamos"].iloc[0]
                st.markdown(f"- **{cat}**: {count} reclamos")

    # Tabla detallada
    st.subheader("Tabla detallada")
    cols_order = [c for c in ["nid","fecha","aerolinea","categoria","origen","destino","titulo","url"] if c in df_f.columns]
    st.dataframe(df_f[cols_order].sort_values(by=["fecha"], ascending=False) if cols_order else df_f)

else:
    st.info("👆 Sube un .xlsx o agrega Con_mas_info_recategorized.xlsx al repo para ver el dashboard.")
