# -*- coding: utf-8 -*-
# Caliente Tenis → Partidos del 1 de noviembre → Excel
# Modos: Selenium (si hay Chrome), Subir HTML, Pegar HTML

import io
import re
import time
import shutil
import platform
from datetime import datetime
from typing import List, Dict, Optional

import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup

TARGET_DAY = 1
TARGET_MONTH = 11
TARGET_YEAR = datetime.now().year

def norm_text(x: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())

def possible_time(txt: str) -> Optional[str]:
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", txt)
    return m.group(0) if m else None

def try_parse_match_row(el) -> Optional[Dict]:
    txt = norm_text(el.get_text(" ", strip=True))
    if not txt:
        return None
    m_vs = re.search(r"(.+?)\s+(?:v\.?|vs\.?)\s+(.+)", txt, flags=re.I)
    if not m_vs:
        parts = [p for p in re.split(r"\s{2,}", txt) if p]
        if len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts[:2]):
            p1, p2 = parts[0], parts[1]
        else:
            return None
    else:
        p1, p2 = m_vs.group(1), m_vs.group(2)

    p1 = norm_text(p1)
    p2 = norm_text(p2)
    hhmm = possible_time(txt)

    info_extra = ""
    m_round = re.search(r"(Ronda|Round|Semifinal|Quarter|Final|Cuartos|Octavos)", txt, flags=re.I)
    if m_round:
        info_extra = m_round.group(0)

    if 2 <= len(p1) <= 60 and 2 <= len(p2) <= 60:
        return {"hora_aprox": hhmm or "", "jugador_a": p1, "jugador_b": p2, "extra": info_extra}
    return None

def parse_html_for_matches(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for cls in [
        "event", "event-card", "market", "coupon", "selection", "match",
        "KambiBC-event", "EventGroup", "EventItem", "participant", "src-EventMarket"
    ]:
        candidates.extend(soup.select(f".{cls}"))
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
    return rows

def to_excel_download(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Juegos_1_Noviembre")
    return buf.getvalue()

st.set_page_config(page_title="Caliente Tenis → Excel (1 Nov)", page_icon="🎾", layout="wide")
st.title("🎾 Caliente (Tenis) → Exportar partidos del 1 de noviembre a Excel")

st.markdown("""
**Modos de entrada**:
1. **Scrape en vivo (Selenium)** — requiere **Google Chrome** en el sistema.  
2. **Subir HTML** — sube un `.html` guardado de la página.  
3. **Pegar HTML** — pega el código fuente de la página.
""")

mode = st.radio("Elige el modo", ["Scrape en vivo (Selenium)", "Subir HTML", "Pegar HTML"])
rows: List[Dict] = []

def chrome_is_available() -> bool:
    # Busca binarios comunes
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"),
        shutil.which("C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"),
        shutil.which("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
    return any(c for c in candidates if c)

if mode == "Scrape en vivo (Selenium)":
    url = st.text_input("URL a scrapear", value="https://sports.caliente.mx/es_MX/Tenis")
    scroll_secs = st.slider("Segundos de scroll/carga (más tiempo = más eventos)", 3, 40, 12)
    run = st.button("Iniciar scraping")

    if run:
        if not chrome_is_available():
            st.error(
                "No se encontró **Google Chrome** en este entorno. "
                "Si estás en **Streamlit Cloud**, usa *Subir HTML* o *Pegar HTML*. "
                "En tu PC, instala Google Chrome y vuelve a intentar."
            )
        else:
            with st.spinner("Abriendo navegador y cargando la página…"):
                html = ""
                try:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options
                    from selenium.webdriver.chrome.service import Service
                    from webdriver_manager.chrome import ChromeDriverManager

                    opts = Options()
                    opts.add_argument("--headless=new")
                    opts.add_argument("--no-sandbox")
                    opts.add_argument("--disable-gpu")
                    opts.add_argument("--disable-dev-shm-usage")
                    opts.add_argument("--window-size=1920,1080")

                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=opts)

                    driver.set_page_load_timeout(60)
                    driver.get(url)
                    time.sleep(4)

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

if rows:
    df = pd.DataFrame(rows)
    try:
        df["_orden_hora"] = df["hora_aprox"].apply(
            lambda x: datetime.strptime(x, "%H:%M").time() if x else datetime.min.time()
        )
        df = df.sort_values(by=["_orden_hora", "jugador_a", "jugador_b"]).drop(columns=["_orden_hora"])
    except Exception:
        df = df.sort_values(by=["jugador_a", "jugador_b"])

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
