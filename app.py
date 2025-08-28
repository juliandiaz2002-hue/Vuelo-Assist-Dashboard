# app.py
# Dashboard de reclamos (Excel) — listo para Replit/Streamlit
# Requisitos: streamlit, pandas, plotly, openpyxl

import io
import unicodedata
from datetime import date
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Dashboard de Reclamos", layout="wide")
st.title("📊 Dashboard de Reclamos de Aerolíneas")

st.markdown(
    "Sube tu archivo **Excel** (.xlsx) con columnas como: `nid`, `fecha`, `categoria`, `aerolinea`, `origen`, `destino`, `titulo`, `url`, etc."
)

file = st.file_uploader("Subir Excel .xlsx", type=["xlsx"]) 

def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    # quita acentos/diacríticos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s


def _normalize_colname(name: str) -> str:
    s = _normalize_text(name)
    # reemplaza separadores no alfanuméricos por guion bajo
    s = "".join(ch if ch.isalnum() else "_" for ch in s)
    s = "_".join(filter(None, s.split("_")))
    # sinónimos comunes -> nombres esperados
    synonyms = {
        "aerolinea": "aerolinea",
        "aerolineas": "aerolinea",
        "aerolinea_nombre": "aerolinea",
        "categoria": "categoria",
        "categorias": "categoria",
        "origen": "origen",
        "destino": "destino",
        "fecha": "fecha",
        "titulo": "titulo",
        "url": "url",
        "nid": "nid",
    }
    return synonyms.get(s, s)


@st.cache_data(show_spinner=False)
def load_df(file_bytes: bytes) -> pd.DataFrame:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, engine="openpyxl")
    except Exception:
        # fallback a motor por defecto
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0)

    # normaliza nombres de columnas
    df.columns = [_normalize_colname(c) for c in df.columns]

    # fecha a datetime (si existe)
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    # columnas esperadas (si faltan, crear)
    for col in ["categoria", "aerolinea", "origen", "destino", "titulo", "url", "nid"]:
        if col not in df.columns:
            df[col] = np.nan

    # limpieza ligera de texto para campos claves
    for c in ["categoria", "aerolinea", "origen", "destino"]:
        if c in df.columns:
            df[c] = (
                df[c]
                .astype(str)
                .replace({"nan": np.nan})
                .map(lambda x: x.strip() if isinstance(x, str) else x)
            )

    # dtypes más compactos
    for c in ["categoria", "aerolinea"]:
        if c in df.columns:
            df[c] = df[c].astype("category")

    return df

# Función para crear esquema de colores personalizado
def get_custom_colors(categories):
    """Crea un esquema de colores personalizado destacando categorías importantes"""
    # Definir claves normalizadas
    important_colors = {
        "cancelacion": "#FF6B6B",            # Rojo coral
        "overbooking": "#4ECDC4",            # Turquesa
        "retraso": "#45B7D1",                # Azul
        "perdida o dano de maleta": "#96CEB4" # Verde suave
    }

    default_color = "#E0E0E0"  # Gris claro
    color_map = {}
    for cat in categories:
        key = _normalize_text(cat)
        color_map[cat] = important_colors.get(key, default_color)
    return color_map

if file:
    df = load_df(file.read())

    # Filtros (en barra lateral)
    st.sidebar.header("Filtros")
    aerolinea_sel = st.sidebar.multiselect(
        "Aerolínea",
        options=sorted([x for x in df["aerolinea"].dropna().unique()]),
    )
    categoria_sel = st.sidebar.multiselect(
        "Categoría",
        options=sorted([x for x in df["categoria"].dropna().unique()]),
    )
    # Rango de fechas
    if "fecha" in df.columns and pd.api.types.is_datetime64_any_dtype(df["fecha"]):
        min_d, max_d = df["fecha"].min(), df["fecha"].max()
        if pd.notnull(min_d) and pd.notnull(max_d):
            rango = st.sidebar.date_input(
                "Rango de fechas",
                value=(min_d.date(), max_d.date()),
            )
        else:
            rango = None
    else:
        rango = None
    # Top N para rutas
    top_n = st.sidebar.slider("Top N rutas", min_value=5, max_value=30, value=15, step=1)

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
        df_f = df_f.copy()
        df_f["dia_semana"] = df_f["fecha"].dt.day_name().map(dow_map)
        df_f["anio_mes"] = df_f["fecha"].dt.to_period("M")

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
                x="categoria", 
                y="reclamos", 
                title="Reclamos por categoría",
                color="categoria",
                color_discrete_map=custom_colors
            )
            fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
            fig.update_xaxes(categoryorder="total descending")
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if df_f["aerolinea"].notna().any():
            fig = px.bar(
                df_f.groupby("aerolinea").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False),
                x="aerolinea", y="reclamos", title="Reclamos por aerolínea"
            )
            fig.update_xaxes(categoryorder="total descending")
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
        if df_f[["origen","destino"]].notna().values.any():
            rutas = (
                df_f.groupby(["origen","destino"]).size().reset_index(name="reclamos")
                .sort_values("reclamos", ascending=False).head(top_n)
            )
            rutas["ruta"] = rutas["origen"].fillna("?") + " → " + rutas["destino"].fillna("?")
            fig = px.bar(rutas, x="reclamos", y="ruta", orientation="h", title=f"Top rutas con más reclamos (Top {top_n})")
            st.plotly_chart(fig, use_container_width=True)

    # Tendencia temporal
    st.subheader("Tendencia temporal")
    if "anio_mes" in df_f.columns:
        serie = (
            df_f.groupby("anio_mes").size().reset_index(name="reclamos")
            .sort_values("anio_mes")
        )
        # convertir Period -> timestamp para ordenar y mostrar bonito
        serie["anio_mes_str"] = serie["anio_mes"].dt.to_timestamp().dt.strftime("%Y-%m")
        fig = px.line(serie, x="anio_mes_str", y="reclamos", markers=True, title="Reclamos por mes")
        st.plotly_chart(fig, use_container_width=True)

    # Gráfico de categorías con colores destacados
    st.subheader("📊 Categorías destacadas")
    if df_f["categoria"].notna().any():
        cat_counts = df_f.groupby("categoria").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False)
        custom_colors = get_custom_colors(cat_counts["categoria"].tolist())
        
        # Crear gráfico de barras horizontal para mejor visualización
        fig = px.bar(
            cat_counts,
            x="reclamos",
            y="categoria",
            orientation="h",
            title="Reclamos por categoría (categorías importantes destacadas)",
            color="categoria",
            color_discrete_map=custom_colors
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Mostrar leyenda de colores especiales (insensible a acentos/mayúsculas)
        st.markdown("**🎨 Categorías destacadas:**")
        display_map = {
            "cancelacion": "Cancelación",
            "overbooking": "Overbooking",
            "retraso": "Retraso",
            "perdida o dano de maleta": "Pérdida o daño de maleta",
        }
        # construimos un índice normalizado -> conteo
        norm_counts = (
            cat_counts.assign(_k=cat_counts["categoria"].map(_normalize_text))
            .groupby("_k")["reclamos"].sum()
        )
        for k, display in display_map.items():
            if k in norm_counts.index:
                st.markdown(f"- **{display}**: {int(norm_counts[k])} reclamos")

    # Tabla detallada
    st.subheader("Tabla detallada")
    cols_order = [c for c in ["nid","fecha","aerolinea","categoria","origen","destino","titulo","url"] if c in df_f.columns]
    table_df = df_f[cols_order].copy() if cols_order else df_f.copy()
    if "fecha" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["fecha"]):
        table_df = table_df.sort_values(by=["fecha"], ascending=False)
    st.dataframe(table_df)

    # Descarga del dataset filtrado
    csv = table_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar CSV (filtrado)", data=csv, file_name="reclamos_filtrado.csv", mime="text/csv")

else:
    st.info("👆 Sube un .xlsx para ver el dashboard.")
