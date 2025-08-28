# app.py
# Dashboard de reclamos (Excel) — listo para Streamlit/Cloud
# Requisitos: streamlit, pandas, plotly, openpyxl

import io
import os
from typing import Optional, List, Union
import unicodedata
from datetime import date
import numpy as np
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Dashboard de Reclamos", layout="wide")
st.title("📊 Dashboard de Reclamos Aéreos")
st.markdown(
    "Sube tu archivo **Excel** (.xlsx) con columnas como: `nid`, `fecha`, `categoria`, `aerolinea`, `origen`, `destino`, `titulo`, `url`, etc."
)

# Fuente de datos
PUBLIC_XLSX_PATH = "Con_mas_info_recategorized.xlsx"
source_mode = st.sidebar.selectbox(
    "Fuente de datos",
    ["Auto (archivo o base incluida)", "URL pública"],
    help="Auto usa el archivo subido si existe; si no, la base incluida en el repo.",
)

# Preferencias de visualización (no específicas de móvil)

url_publica = None
if source_mode == "URL pública":
    url_publica = st.sidebar.text_input(
        "URL pública (raw .xlsx)",
        placeholder="https://.../dataset.xlsx",
        help="Puede ser un enlace RAW de GitHub o cualquier URL directa al .xlsx",
    )

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
        # columnas para tramo / internacionalidad
        "tramo": "tramo",
        "tipo_tramo": "tramo",
        "nacional_internacional": "tramo",
        "internacional": "internacional",
        "es_internacional": "internacional",
    }
    return synonyms.get(s, s)


@st.cache_data(show_spinner=False)
def load_df(file_bytes: bytes, sheet_name=0) -> pd.DataFrame:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine="openpyxl")
    except Exception:
        # fallback a motor por defecto
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)

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


@st.cache_data(show_spinner=False)
def get_sheet_names(file_bytes: bytes) -> List[str]:
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    except Exception:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    return list(xls.sheet_names)


def read_local_bytes(path: str) -> Optional[bytes]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def fetch_url_bytes(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

# Config para deshabilitar zoom en Plotly y helper para bloquear ejes
STATIC_CONFIG = dict(displayModeBar=False, staticPlot=True)

def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

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

data_bytes = None
data_label = None
if source_mode == "URL pública":
    if url_publica:
        data_bytes = fetch_url_bytes(url_publica)
        data_label = "URL pública"
        if data_bytes is None:
            st.error("No se pudo descargar el Excel desde la URL proporcionada.")
else:
    file = st.file_uploader("Subir Excel .xlsx", type=["xlsx"])
    if file is not None:
        data_bytes = file.read()
        data_label = "Archivo subido"
    else:
        # fallback a base incluida
        data_bytes = read_local_bytes(PUBLIC_XLSX_PATH)
        if data_bytes is not None:
            data_label = f"Base incluida: {PUBLIC_XLSX_PATH}"

if data_bytes:
    # Selección de hoja si hay varias
    sheet_names = get_sheet_names(data_bytes)
    sheet_name = 0
    if len(sheet_names) > 1:
        sheet_name = st.sidebar.selectbox("Hoja", options=sheet_names, index=0)
    df = load_df(data_bytes, sheet_name=sheet_name)
    if data_label:
        st.caption(f"Usando datos de: {data_label}")

    # Filtros (en barra lateral)
    st.sidebar.header("Filtros")
    # Botón para limpiar filtros
    if st.sidebar.button("Limpiar filtros"):
        for k in ["aerolinea_sel", "categoria_sel", "rango", "top_n"]:
            if k in st.session_state:
                del st.session_state[k]
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()
    aerolinea_sel = st.sidebar.multiselect(
        "Aerolínea",
        options=sorted([x for x in df["aerolinea"].dropna().unique()]),
        key="aerolinea_sel",
    )
    categoria_sel = st.sidebar.multiselect(
        "Categoría",
        options=sorted([x for x in df["categoria"].dropna().unique()]),
        key="categoria_sel",
    )
    # Rango de fechas
    if "fecha" in df.columns and pd.api.types.is_datetime64_any_dtype(df["fecha"]):
        min_d, max_d = df["fecha"].min(), df["fecha"].max()
        if pd.notnull(min_d) and pd.notnull(max_d):
            rango = st.sidebar.date_input(
                "Rango de fechas",
                value=(min_d.date(), max_d.date()),
                key="rango",
            )
        else:
            rango = None
    else:
        rango = None
    # Top N para rutas
    top_n = st.sidebar.slider("Top N rutas", min_value=5, max_value=30, value=15, step=1, key="top_n")

    df_f = df.copy()
    if aerolinea_sel:
        df_f = df_f[df_f["aerolinea"].isin(aerolinea_sel)]
    if categoria_sel:
        df_f = df_f[df_f["categoria"].isin(categoria_sel)]
    if rango and len(rango) == 2:
        df_f = df_f[
            (df_f["fecha"].dt.date >= rango[0]) & 
            (df_f["fecha"].dt.date <= rango[1])
        ]

    # Derivar bandera de internacionalidad desde posibles columnas
    # Preferencia: columna booleana/flag "internacional" o una categórica "tramo" con valores como "nacional"/"internacional"
    df_f = df_f.copy()
    internacional_flag = None
    if "internacional" in df_f.columns:
        # Normaliza a booleano/categórico legible
        def _to_bool_internacional(x):
            if pd.isna(x):
                return np.nan
            sx = str(x).strip().lower()
            # acepta 1/0, true/false, si/no, internacional/nacional
            if sx in {"1", "true", "t", "si", "sí", "internacional", "int"}:
                return True
            if sx in {"0", "false", "f", "no", "nacional", "nac"}:
                return False
            return np.nan
        df_f["_internacional_bool"] = df_f["internacional"].map(_to_bool_internacional)
        df_f["internacional_flag"] = df_f["_internacional_bool"].map({True: "Internacional", False: "Nacional"})
        internacional_flag = "internacional_flag"
    elif "tramo" in df_f.columns:
        def _to_flag_from_tramo(x):
            if pd.isna(x):
                return np.nan
            sx = str(x).strip().lower()
            if "internacional" in sx or sx in {"inter", "int"}:
                return "Internacional"
            if "nacional" in sx or sx in {"nac", "nacional"}:
                return "Nacional"
            return np.nan
        df_f["internacional_flag"] = df_f["tramo"].map(_to_flag_from_tramo)
        internacional_flag = "internacional_flag"

    # Preparar datos para visualizaciones
    if "fecha" in df_f.columns and pd.api.types.is_datetime64_any_dtype(df_f["fecha"]):
        dow_map = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        df_f = df_f.copy()
        df_f["dia_semana"] = df_f["fecha"].dt.day_name().map(dow_map)
        df_f["anio_mes"] = df_f["fecha"].dt.to_period("M")

    # Validaciones y KPIs
    if "fecha" in df.columns and df["fecha"].isna().mean() > 0.5:
        st.warning("Más del 50% de las fechas no pudieron parsearse (NaT). Verifica el formato de la columna 'fecha'.")
    missing_cols = [c for c in ["categoria", "aerolinea"] if c not in df.columns]
    if missing_cols:
        st.warning(f"Faltan columnas esperadas: {', '.join(missing_cols)}. Algunas visualizaciones podrían no mostrarse.")

    # KPIs
    total = len(df_f)
    st.header(f"📈 KPIs - Total: {total:,} reclamos")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total reclamos", f"{total:,}")
    with col2:
        if "categoria" in df_f.columns and df_f["categoria"].notna().any():
            st.metric("Categorías únicas", int(df_f["categoria"].nunique()))
    with col3:
        if "aerolinea" in df_f.columns and df_f["aerolinea"].notna().any():
            st.metric("Aerolíneas", int(df_f["aerolinea"].nunique()))
    with col4:
        if "origen" in df_f.columns and "destino" in df_f.columns:
            st.metric("Rutas únicas", int(df_f.groupby(["origen", "destino"]).ngroups))

    # Gráficos principales
    st.subheader("📊 Análisis por categoría y aerolínea")
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
                color_discrete_map=custom_colors,
            )
            fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
            fig.update_xaxes(categoryorder="total descending", tickangle=-35)
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
    with c2:
        if df_f["aerolinea"].notna().any():
            air_counts = df_f.groupby("aerolinea").size().reset_index(name="reclamos").sort_values("reclamos", ascending=False)
            fig = px.bar(
                air_counts,
                x="aerolinea",
                y="reclamos",
                title="Reclamos por aerolínea",
            )
            fig.update_xaxes(categoryorder="total descending", tickangle=-35)
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)

    c3, c4 = st.columns(2)
    with c3:
        if "dia_semana" in df_f.columns:
            fig = px.bar(
                df_f.groupby("dia_semana").size().reset_index(name="reclamos"),
                x="dia_semana", y="reclamos", title="Reclamos por día de la semana"
            )
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
    with c4:
        # Reservado para el nuevo bloque de ubicación
        pass

    # Bloque de visualizaciones relacionadas a lugares
    st.subheader("🌍 Análisis por ubicación")
    c_loc1, c_loc2, c_loc3 = st.columns(3)

    # 1) Nacional vs Internacional
    with c_loc1:
        if internacional_flag and df_f[internacional_flag].notna().any():
            counts = (
                df_f.groupby(internacional_flag).size().reset_index(name="reclamos")
                .sort_values("reclamos", ascending=False)
            )
            fig = px.bar(
                counts,
                x=internacional_flag,
                y="reclamos",
                title="Reclamos: Nacional vs Internacional",
                color=internacional_flag,
                color_discrete_map={"Nacional": "#4E79A7", "Internacional": "#F28E2B"},
            )
            fig.update_layout(legend_title_text="Tipo de vuelo")
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
        else:
            st.info("No se encontró columna de tramo/internacional para derivar Nacional vs Internacional.")

    # 2) Top destinos
    with c_loc2:
        if "destino" in df_f.columns and df_f["destino"].notna().any():
            dest_counts = (
                df_f.groupby("destino").size().reset_index(name="reclamos")
                .sort_values("reclamos", ascending=False).head(top_n)
            )
            fig = px.bar(dest_counts, x="reclamos", y="destino", orientation="h", title=f"Top destinos con más reclamos (Top {top_n})")
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
        else:
            st.info("No hay datos de destinos para mostrar.")

    # 3) Top orígenes
    with c_loc3:
        if "origen" in df_f.columns and df_f["origen"].notna().any():
            orig_counts = (
                df_f.groupby("origen").size().reset_index(name="reclamos")
                .sort_values("reclamos", ascending=False).head(top_n)
            )
            fig = px.bar(orig_counts, x="reclamos", y="origen", orientation="h", title=f"Top orígenes con más reclamos (Top {top_n})")
            st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
        else:
            st.info("No hay datos de orígenes para mostrar.")

    # Tendencia temporal
    st.subheader("📈 Tendencia temporal")
    if "anio_mes" in df_f.columns:
        serie = (
            df_f.groupby("anio_mes").size().reset_index(name="reclamos")
            .sort_values("anio_mes")
        )
        # convertir Period -> timestamp para ordenar y mostrar bonito
        serie["anio_mes_str"] = serie["anio_mes"].dt.to_timestamp().dt.strftime("%Y-%m")
        fig = px.line(serie, x="anio_mes_str", y="reclamos", markers=True, title="Reclamos por mes")
        st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)

    # Gráfico de categorías con colores destacados
    st.subheader("🎨 Análisis detallado por categoría")
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
        st.plotly_chart(lock_axes(fig), use_container_width=True, config=STATIC_CONFIG)
        
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
    st.subheader("📋 Tabla detallada")
    cols_order = [c for c in ["nid","fecha","aerolinea","categoria","origen","destino","titulo","url"] if c in df_f.columns]
    table_df = df_f[cols_order].copy() if cols_order else df_f.copy()
    if "fecha" in table_df.columns and pd.api.types.is_datetime64_any_dtype(table_df["fecha"]):
        table_df = table_df.sort_values(by=["fecha"], ascending=False)
    st.dataframe(table_df, use_container_width=True)

    # Descarga del dataset filtrado
    csv = table_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar CSV (filtrado)", data=csv, file_name="reclamos_filtrado.csv", mime="text/csv")

else:
    st.info("👆 Sube un .xlsx o ingresa una URL pública desde la barra lateral. Si existe una base incluida, se usará automáticamente.")
