import re

import pandas as pd
import streamlit as st
from PIL import Image

# ---------------------------------------------------------------
# Configuracion general
# ---------------------------------------------------------------
st.set_page_config(page_title="Analisis de sensores ESP32", page_icon="🌡️", layout="wide")

UMBRAL_TEMP = 30   # °C, mismo umbral usado en el proyecto IoT
UMBRAL_HUM = 80    # %

NOMBRES = {
    "temperatura": "Temperatura (°C)",
    "humedad": "Humedad (%)",
}


def nombre_limpio(columna: str) -> str:
    """Convierte encabezados de Grafana a un nombre corto.

    Ejemplos:
      'temperatura {dispositivo="ESP32", name="Sensor 1"}' -> 'Temperatura (°C)'
      'temperatura ESP32'                                  -> 'Temperatura (°C)'
    """
    base = re.split(r"[{]", str(columna))[0].strip().lower()
    for clave, bonito in NOMBRES.items():
        if base.startswith(clave):
            return bonito
    return str(columna).strip()


def cargar_datos(archivo) -> pd.DataFrame:
    """Lee el CSV exportado desde Grafana y lo deja listo para analizar."""
    df = pd.read_csv(archivo)

    # La columna de tiempo suele llamarse 'Time'; si no, se usa la primera
    col_tiempo = "Time" if "Time" in df.columns else df.columns[0]
    df = df.rename(columns={col_tiempo: "Tiempo"})
    df = df.rename(columns={c: nombre_limpio(c) for c in df.columns if c != "Tiempo"})

    df["Tiempo"] = pd.to_datetime(df["Tiempo"], errors="coerce")
    df = df.dropna(subset=["Tiempo"]).set_index("Tiempo").sort_index()

    # Solo columnas numericas (las mediciones)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(axis=1, how="all").dropna(how="all")
    return df


# ---------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------
st.title("🌡️ Análisis de datos de sensores ESP32")
st.write(
    "Datos de temperatura y humedad medidos por un **ESP32 con sensor DHT22** simulado en Wokwi, "
    "guardados en **InfluxDB** y exportados desde **Grafana** en formato CSV."
)

try:
    st.image(Image.open("grafana2.jpg"), caption="Flujo: Wokwi → InfluxDB → Grafana → CSV → Streamlit")
except FileNotFoundError:
    pass

archivo = st.file_uploader("Sube el CSV descargado desde Grafana", type=["csv"])

if archivo is None:
    st.info("Sube el archivo CSV para comenzar el análisis (Grafana → Inspect → Data → Download CSV).")
    st.stop()

try:
    df = cargar_datos(archivo)
except Exception as error:
    st.error(f"No se pudo leer el archivo: {error}")
    st.stop()

if df.empty:
    st.error("El archivo no tiene datos numéricos para analizar.")
    st.stop()

variables = list(df.columns)
temp = NOMBRES["temperatura"] if NOMBRES["temperatura"] in variables else None
hum = NOMBRES["humedad"] if NOMBRES["humedad"] in variables else None

if len(df) < 10:
    st.warning(
        f"El archivo solo tiene {len(df)} lecturas. Para un análisis más confiable, "
        "deja correr la simulación más tiempo antes de exportar."
    )

# ---------------------------------------------------------------
# Resumen rapido
# ---------------------------------------------------------------
st.header("Resumen")
inicio, fin = df.index.min(), df.index.max()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Lecturas", len(df))
c2.metric("Periodo", f"{inicio:%H:%M} – {fin:%H:%M}")
if temp:
    c3.metric("Temperatura promedio", f"{df[temp].mean():.1f} °C")
if hum:
    c4.metric("Humedad promedio", f"{df[hum].mean():.1f} %")

# ---------------------------------------------------------------
# Graficas
# ---------------------------------------------------------------
st.header("Comportamiento en el tiempo")
pestanas = st.tabs(["Todas las variables"] + variables)
with pestanas[0]:
    st.line_chart(df)
for pestana, variable in zip(pestanas[1:], variables):
    with pestana:
        st.line_chart(df[[variable]])

# ---------------------------------------------------------------
# Estadisticos
# ---------------------------------------------------------------
st.header("Estadísticos básicos")
estadisticos = df.describe().rename(
    index={
        "count": "Cantidad",
        "mean": "Promedio",
        "std": "Desviación estándar",
        "min": "Mínimo",
        "25%": "Percentil 25",
        "50%": "Mediana",
        "75%": "Percentil 75",
        "max": "Máximo",
    }
)
st.dataframe(estadisticos.round(2), use_container_width=True)

# ---------------------------------------------------------------
# Alertas por umbral
# ---------------------------------------------------------------
st.header("Alertas por umbral")
a1, a2 = st.columns(2)
if temp:
    altas = df[df[temp] > UMBRAL_TEMP]
    a1.metric(f"Lecturas con temperatura > {UMBRAL_TEMP} °C", len(altas),
              f"{len(altas) / len(df):.0%} del total", delta_color="off")
if hum:
    humedas = df[df[hum] > UMBRAL_HUM]
    a2.metric(f"Lecturas con humedad > {UMBRAL_HUM} %", len(humedas),
              f"{len(humedas) / len(df):.0%} del total", delta_color="off")

# ---------------------------------------------------------------
# Filtros interactivos
# ---------------------------------------------------------------
st.header("Filtrar lecturas")
filtrado = df.copy()
for variable in variables:
    minimo, maximo = float(df[variable].min()), float(df[variable].max())
    if minimo == maximo:
        st.caption(f"{variable}: todas las lecturas valen {minimo:g}, no hay rango para filtrar.")
        continue
    rango = st.slider(
        f"Rango de {variable}",
        min_value=minimo,
        max_value=maximo,
        value=(minimo, maximo),
        key=f"filtro_{variable}",
    )
    filtrado = filtrado[filtrado[variable].between(rango[0], rango[1])]

st.write(f"**{len(filtrado)}** de {len(df)} lecturas cumplen los filtros.")
st.dataframe(filtrado, use_container_width=True)
st.download_button(
    "Descargar lecturas filtradas (CSV)",
    filtrado.to_csv().encode("utf-8"),
    file_name="lecturas_filtradas.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------
# Relacion entre temperatura y humedad
# ---------------------------------------------------------------
if temp and hum:
    st.header("Relación entre temperatura y humedad")
    variacion = df[temp].nunique() > 1 and df[hum].nunique() > 1
    if len(df) >= 3 and variacion:
        correlacion = df[temp].corr(df[hum])
        st.scatter_chart(df, x=temp, y=hum)
        if abs(correlacion) < 0.3:
            lectura = "prácticamente no hay relación lineal entre ambas variables"
        elif correlacion > 0:
            lectura = "cuando sube la temperatura, la humedad tiende a subir"
        else:
            lectura = "cuando sube la temperatura, la humedad tiende a bajar"
        st.write(f"Coeficiente de correlación: **{correlacion:.2f}**, es decir, {lectura}.")
    else:
        st.caption("Se necesitan al menos 3 lecturas con valores distintos para calcular la correlación.")
