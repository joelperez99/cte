# -*- coding: utf-8 -*-
# streamlit_app.py — Caliente Tenis → Partidos del 1 de noviembre → Excel
# Modos:
#  1) Scrape en vivo con Selenium
#  2) Subir HTML guardado
#  3) Pegar HTML
#
# Salida: tabla de partidos (hora local del sitio cuando esté disponible) y botón para descargar Excel.

import io
import re
import time
from datetime import datetime, date
from typing import List, Dict, Optional

import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup

# ------------------------ Utilidades ------------------------ #

TARGET_DAY = 1         # 1 de noviembre
TARGET_MONTH = 11
TARGET_YEAR = datetime.now().year  # asume año actual

def norm_text(x: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())

def possible_time(txt: str) -> Optional[str]:
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", txt)
    return m.group(0) if m else None

def try_parse_match_row(el) -> Optional[Dict]:
    """
    Heurística de extracción: intenta hallar "Jugador A" vs "Jugador B" y hora si existe.
    Funciona con varios layouts típicos de casas de apuesta.
    """
    txt = norm_text(el.get_text(" ", strip=True))
    if not txt:
        return None

    # Patrones típicos: "Jugador A v Jugador B", "Jugador A vs Jugador B"
    m_vs = re.search(r"(.+?)\s+(?:v\.?|vs\.?)\s+(.+)", txt, flags=re.I)
    if not m_vs:
        # fallback: cuando aparecen los nombres en bloques separados
        # Buscamos dos nombres con letras y posible inicial.
        parts = [p for p in re.split(r"\s{2,}", txt) if p]
        if len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts[:2]):
            p1, p2 = parts[0], parts[1]
        else:
            return None
    else:
        p1, p2 = m_vs.group(1), m_vs.group(2)

    # limpiar restos muy largos
    p1 = norm_text(p1)
    p2 = norm_text(p2)

    # hora si está visible
    hhmm = possible_time(txt)

    # A veces el torneo/round aparece; intentemos capturarlo corto
    # (lo dejamos en blanco si no es claro)
    info_extra = ""
    m_round = re.search(r"(Ronda|Round|Semifinal|Quarter|Final|Cuartos|Octavos)", txt, flags=re.I)
    if m_round:
        info_extra = m_round.group(0)

    # filtro mínimo de sanidad
    if 2 <= len(p1) <= 60 and 2 <= len(p2) <= 60:
        return {
            "hora_aprox": hhmm or "",
            "jugador_a": p1,
            "jugador_b": p2,
            "extra": info_extra
        }
    return None

def parse_html_for_matches(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    # Candidatos de contenedores: tarjetas/eventos típicos
    candidates = []
    # 1) por clases habituales
    for cls in [
        "event", "event-card", "market", "coupon", "selection", "match",
        "KambiBC-event", "EventGroup", "EventItem", "participant", "src-EventMarket"
    ]:
        candidates.extend(soup.select(f".{cls}"))
    # 2) por roles genéricos
    candidates.extend(soup.select("[role=row], [role=listitem], article, li"))

    seen = set()
    rows = []
    for el in candidates:
        item = try_parse_match_row(el)
        if item:
            key = (item["hora_aprox"], item["jugador_a"], item["jugador_b"])
            if key not in seen:
                seen.add(key)
                rows.append(item)

    # Si no encontramos nada, como plan C intenta por líneas con " vs "
    if not rows:
        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            line = norm_text(line)
            if re.search(r"\s(?:v\.?|vs\.?)\s", line, flags=re.I):
                m = re.search(r"(.+?)\s+(?:v\.?|vs\.?)\s+(.+)", line, flags=re.I)
                if m:
                    p1, p2 = norm_text(m.group(1)), norm_text(m.group(2))
                    hhmm = possible_time(line) or ""
                    key = (hhmm, p1, p2)
                    if key not in seen and 2 <= len(p1) <= 60 and 2 <= len(p2) <= 60:
                        rows.append({"hora_aprox": hhmm, "jugador_a": p1, "jugador_b": p2, "extra": ""})
                        seen.add(key)

    return rows

def filter_by_target_date(rows: List[Dict]) -> List[Dict]:
    """
    Muchas casas no imprimen fecha explícita por partido en el listado diario.
    Asumimos que si abriste la URL del día 1 de noviembre o estás en el feed 'hoy/mañana',
    ya es el set del día. Aquí solo devolvemos tal cual.
    Si detectas la fecha en el HTML, aquí podrías validar (quedó preparado para extender).
    """
    # Placeholder: retornar todo. Si extraes fecha, filtra aquí.
    return rows

def to_excel_download(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Juegos_1_Noviembre")
    return buf.getvalue()

# ------------------------ UI ------------------------ #

st.set_page_config(page_title="Caliente Tenis → Excel (1 Nov)", page_icon="🎾", layout="wide")
st.title("🎾 Caliente (Tenis) → Exportar partidos del 1 de noviembre a Excel")

st.markdown("""
**Tres modos de entrada**:
1. **Scrape en vivo** (necesita Chrome instalado).  
2. **Subir HTML** (archivo guardado de la página).  
3. **Pegar HTML** (copiar/pegar el código fuente).
""")

mode = st.radio("Elige el modo", ["Scrape en vivo (Selenium)", "Subir HTML", "Pegar HTML"])

rows: List[Dict] = []

if mode == "Scrape en vivo (Selenium)":
    st.info("Este modo abre un navegador en segundo plano, carga la página y recoge los partidos.")
    url = st.text_input("URL a scrapear", value="https://sports.caliente.mx/es_MX/Tenis")
    scroll_secs = st.slider("Segundos de scroll/carga (más tiempo = más eventos)", 3, 40, 12)
    run = st.button("Iniciar scraping")

    if run:
        with st.spinner("Abriendo navegador y cargando la página…"):
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                from webdriver_manager.chrome import ChromeDriverManager

                opts = Options()
                opts.add_argument("--headless=new")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                driver = webdriver.Chrome(ChromeDriverManager().install(), options=opts)
                driver.set_page_load_timeout(60)
                driver.get(url)
                time.sleep(4)  # espera inicial

                # scroll suave para forzar carga perezosa
                t0 = time.time()
                last_h = 0
                while time.time() - t0 < scroll_secs:
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight/3);")
                    time.sleep(1.0)
                    h = driver.execute_script("return document.body.scrollHeight")
                    if h == last_h:
                        break
                    last_h = h

                html = driver.page_source
                driver.quit()
            except Exception as e:
                st.error(f"Error en Selenium: {e}")
                html = ""

        if html:
            parsed = parse_html_for_matches(html)
            rows = filter_by_target_date(parsed)

elif mode == "Subir HTML":
    up = st.file_uploader("Sube el archivo .html de la página", type=["html", "htm"])
    if up:
        html = up.read().decode("utf-8", errors="ignore")
        rows = filter_by_target_date(parse_html_for_matches(html))

elif mode == "Pegar HTML":
    html = st.text_area("Pega aquí el HTML copiado de la página:", height=300)
    if st.button("Procesar HTML pegado"):
        rows = filter_by_target_date(parse_html_for_matches(html))

# ------------------------ Resultados ------------------------ #

if rows:
    df = pd.DataFrame(rows)
    # Ordenar: primero la hora si existe
    def key_h(row):
        if row["hora_aprox"]:
            try:
                return datetime.strptime(row["hora_aprox"], "%H:%M").time()
            except:
                return datetime.min.time()
        return datetime.min.time()

    df = df.sort_values(by=list(df.columns), key=None)  # orden estable
    # Intento mejor: ordenar por hora si existe
    try:
        df["_orden_hora"] = df["hora_aprox"].apply(lambda x: datetime.strptime(x, "%H:%M").time() if x else datetime.min.time())
        df = df.sort_values(by=["_orden_hora", "jugador_a", "jugador_b"]).drop(columns=["_orden_hora"])
    except Exception:
        pass

    st.success(f"Partidos encontrados: {len(df)}")
    st.dataframe(df, use_container_width=True)

    xbytes = to_excel_download(df)
    st.download_button(
        "⬇️ Descargar Excel",
        data=xbytes,
        file_name="caliente_tenis_1_noviembre.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.warning("Aún no hay resultados. Elige un modo y procesa el contenido.")
