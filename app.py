"""
Bus Charging Scheduler - Streamlit UI (Next-Level Dark Theme)
"""

import streamlit as st
import streamlit.components.v1 as components
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from scheduler.models import Scenario, SimulationResult, BusTimeline, StationQueueEntry
from scheduler.scheduler import BusScheduler


def show_table(rows: List[Dict], highlight_col: str = None, highlight_val: int = 0,
               key: str = None, search: bool = False, height: int = None) -> None:
    """
    Fully dark-themed interactive HTML table with:
    - Click-to-sort on every column header (asc/desc toggle)
    - Live search/filter input
    - CSV download button
    All rendered as pure HTML+JS inside st.components so no iframe color bleed.
    """
    if not rows:
        st.markdown('<div class="info-box">No data available.</div>', unsafe_allow_html=True)
        return

    headers = list(rows[0].keys())
    uid = key or "tbl"

    # Build JSON data for JS
    data_json = json.dumps(rows)
    headers_json = json.dumps(headers)
    highlight_col_js = json.dumps(highlight_col or "")
    highlight_val_js = str(highlight_val)

    show_search = "true" if search else "false"
    table_height = f"{height}px" if height else "auto"
    max_height = f"min({height}px, 600px)" if height else "600px"

    html = f"""
<div id="wrap_{uid}" style="font-family:'Rajdhani',sans-serif; margin:0.5rem 0;">

  <!-- Search + Download bar -->
  <div style="display:flex; gap:0.75rem; align-items:center; margin-bottom:0.6rem;"
       id="toolbar_{uid}">
    <input id="search_{uid}" type="text" placeholder="🔍  Search rows…"
      style="display:{'block' if search else 'none'}; flex:1; background:#0d1f35;
             border:1px solid rgba(0,255,200,0.3); border-radius:8px;
             color:#c0d8f0; padding:0.45rem 0.9rem; font-size:0.9rem;
             font-family:'Rajdhani',sans-serif; outline:none;"
      oninput="filterTable_{uid}()"
      onfocus="this.style.borderColor='#00ffc8'; this.style.boxShadow='0 0 10px rgba(0,255,200,0.2)'"
      onblur="this.style.borderColor='rgba(0,255,200,0.3)'; this.style.boxShadow='none'"
    />
    <button onclick="downloadCSV_{uid}()"
      style="background:transparent; border:1px solid rgba(0,255,200,0.4);
             color:#00ffc8; border-radius:6px; padding:0.4rem 1rem;
             font-family:'Rajdhani',sans-serif; font-weight:600; font-size:0.85rem;
             letter-spacing:1px; cursor:pointer; white-space:nowrap;
             transition:all 0.2s;"
      onmouseover="this.style.background='rgba(0,255,200,0.1)'; this.style.boxShadow='0 0 12px rgba(0,255,200,0.2)'"
      onmouseout="this.style.background='transparent'; this.style.boxShadow='none'"
    >⬇ CSV</button>
    <span id="count_{uid}" style="color:rgba(0,255,200,0.5); font-size:0.8rem; white-space:nowrap;"></span>
  </div>

  <!-- Table -->
  <div style="overflow:visible; border-radius:10px;
              border:1px solid rgba(0,255,200,0.2); background:#0a1628;
              padding-bottom:4px;">
    <table id="table_{uid}"
      style="width:100%; border-collapse:collapse; font-size:0.92rem;">
      <thead id="thead_{uid}"></thead>
      <tbody id="tbody_{uid}"></tbody>
    </table>
  </div>
</div>

<script>
(function() {{
  const DATA    = {data_json};
  const HEADERS = {headers_json};
  const HL_COL  = {highlight_col_js};
  const HL_VAL  = {highlight_val_js};
  const UID     = "{uid}";

  let sortCol = null;
  let sortAsc = true;
  let filtered = [...DATA];

  function renderHead() {{
    const thead = document.getElementById('thead_' + UID);
    const tr = document.createElement('tr');
    tr.style.cssText = 'background:#0d1f35; position:sticky; top:0; z-index:2;';
    HEADERS.forEach((h, i) => {{
      const th = document.createElement('th');
      th.style.cssText = `color:#00ffc8; font-weight:700; text-transform:uppercase;
        letter-spacing:1px; font-size:0.75rem; padding:0.7rem 1rem; text-align:left;
        border-bottom:1px solid rgba(0,255,200,0.25); cursor:pointer; user-select:none;
        white-space:nowrap;`;
      const arrow = sortCol === h ? (sortAsc ? ' ▲' : ' ▼') : ' ⇅';
      th.innerHTML = h + `<span style="opacity:0.5; font-size:0.7rem;">${{arrow}}</span>`;
      th.onclick = () => {{
        if (sortCol === h) sortAsc = !sortAsc;
        else {{ sortCol = h; sortAsc = true; }}
        sortData();
        renderHead();
        renderBody();
      }};
      th.onmouseover = () => th.style.color = '#ffffff';
      th.onmouseout  = () => th.style.color = '#00ffc8';
      tr.appendChild(th);
    }});
    thead.innerHTML = '';
    thead.appendChild(tr);
  }}

  function renderBody() {{
    const tbody = document.getElementById('tbody_' + UID);
    tbody.innerHTML = '';
    filtered.forEach((row, ri) => {{
      const tr = document.createElement('tr');
      const waitVal = HL_COL ? Number(row[HL_COL] ?? 0) : 0;
      const hasWait = HL_COL && waitVal > HL_VAL;

      let rowBg, borderLeft, waitColor, badgeBg, badgeText;
      if (hasWait) {{
        if (waitVal >= 30) {{
          rowBg = 'rgba(255,60,60,0.12)'; borderLeft = '3px solid #ff3c3c';
          waitColor = '#ff3c3c'; badgeBg = '#ff3c3c'; badgeText = '#fff';
        }} else if (waitVal >= 15) {{
          rowBg = 'rgba(255,140,0,0.12)'; borderLeft = '3px solid #ff8c00';
          waitColor = '#ff8c00'; badgeBg = '#ff8c00'; badgeText = '#fff';
        }} else {{
          rowBg = 'rgba(255,200,0,0.08)'; borderLeft = '3px solid #ffc800';
          waitColor = '#ffc800'; badgeBg = '#ffc800'; badgeText = '#020b18';
        }}
      }} else {{
        rowBg = ri % 2 === 0 ? '#0a1628' : '#0b1a2e';
        borderLeft = '3px solid transparent';
        waitColor = '#00ff88'; badgeBg = 'rgba(0,255,136,0.15)'; badgeText = '#00ff88';
      }}

      tr.style.cssText = `background:${{rowBg}}; border-left:${{borderLeft}}; transition:background 0.2s;`;
      tr.onmouseover = () => tr.style.background = 'rgba(0,255,200,0.06)';
      tr.onmouseout  = () => tr.style.background = rowBg;

      HEADERS.forEach(h => {{
        const td = document.createElement('td');
        td.style.cssText = 'padding:0.6rem 1rem; border-bottom:1px solid rgba(0,255,200,0.06);';

        if (h === HL_COL) {{
          const badge = document.createElement('span');
          badge.style.cssText = `background:${{badgeBg}}; color:${{badgeText}};
            padding:2px 9px; border-radius:12px; font-size:0.82rem; font-weight:700;`;
          badge.textContent = row[h] !== undefined ? row[h] : '0';
          td.appendChild(badge);
        }} else {{
          td.style.color = '#c0d8f0';
          td.textContent = row[h] !== undefined ? row[h] : '';
        }}
        tr.appendChild(td);
      }});
      tbody.appendChild(tr);
    }});
    const cnt = document.getElementById('count_' + UID);
    if (cnt) cnt.textContent = filtered.length + ' / ' + DATA.length + ' rows';
  }}

  function sortData() {{
    if (!sortCol) return;
    filtered.sort((a, b) => {{
      let va = a[sortCol], vb = b[sortCol];
      const na = Number(va), nb = Number(vb);
      if (!isNaN(na) && !isNaN(nb)) {{ va = na; vb = nb; }}
      else {{ va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }}
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ?  1 : -1;
      return 0;
    }});
  }}

  window['filterTable_' + UID] = function() {{
    const q = document.getElementById('search_' + UID).value.toLowerCase();
    filtered = DATA.filter(row =>
      HEADERS.some(h => String(row[h] ?? '').toLowerCase().includes(q))
    );
    if (sortCol) sortData();
    renderBody();
  }};

  window['downloadCSV_' + UID] = function() {{
    const rows = [HEADERS.join(',')];
    filtered.forEach(row => {{
      rows.push(HEADERS.map(h => JSON.stringify(row[h] ?? '')).join(','));
    }});
    const blob = new Blob([rows.join('\\n')], {{type:'text/csv'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = UID + '.csv';
    a.click();
  }};

  renderHead();
  renderBody();
}})();
</script>
"""
    row_count = len(rows)
    # Each row ~44px + 110px for toolbar/header/padding
    natural_height = row_count * 44 + 110
    # Cap at 480px — beyond that the iframe scrolls (single scrollbar)
    iframe_height = min(natural_height, 480)
    st.components.v1.html(html, height=iframe_height, scrolling=natural_height > 480)


# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="EV Bus Charging Scheduler",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# Custom CSS + Animated Background
# ============================================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&display=swap');

/* ── Animated particle background ── */
body, .stApp {
    background: #020b18 !important;
    font-family: 'Rajdhani', sans-serif !important;
}

.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(ellipse at 20% 50%, rgba(0,255,200,0.04) 0%, transparent 60%),
        radial-gradient(ellipse at 80% 20%, rgba(0,150,255,0.06) 0%, transparent 60%),
        radial-gradient(ellipse at 60% 80%, rgba(120,0,255,0.04) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
    animation: bgPulse 8s ease-in-out infinite alternate;
}

@keyframes bgPulse {
    0%   { opacity: 0.6; }
    100% { opacity: 1; }
}

/* Floating grid lines */
.stApp::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image:
        linear-gradient(rgba(0,255,200,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,255,200,0.03) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
    z-index: 0;
    animation: gridScroll 20s linear infinite;
}

@keyframes gridScroll {
    0%   { transform: translateY(0); }
    100% { transform: translateY(60px); }
}

/* ── Main content above bg ── */
.main .block-container {
    position: relative;
    z-index: 1;
    padding-top: 1rem !important;
}

/* ── Hero header ── */
.hero-header {
    background: linear-gradient(135deg, #0a1628 0%, #0d2137 50%, #0a1628 100%);
    border: 1px solid rgba(0,255,200,0.2);
    border-radius: 16px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 40px rgba(0,255,200,0.08), inset 0 1px 0 rgba(255,255,255,0.05);
}

.hero-header::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: conic-gradient(from 0deg at 50% 50%,
        transparent 0deg,
        rgba(0,255,200,0.03) 60deg,
        transparent 120deg,
        rgba(0,150,255,0.03) 180deg,
        transparent 240deg,
        rgba(120,0,255,0.03) 300deg,
        transparent 360deg);
    animation: heroSpin 15s linear infinite;
}

@keyframes heroSpin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}

.hero-title {
    font-family: 'Orbitron', monospace !important;
    font-size: 2.8rem;
    font-weight: 900;
    background: linear-gradient(90deg, #00ffc8, #00aaff, #7b2fff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    position: relative;
    z-index: 1;
    letter-spacing: 2px;
    animation: titleGlow 3s ease-in-out infinite alternate;
}

@keyframes titleGlow {
    from { filter: drop-shadow(0 0 8px rgba(0,255,200,0.4)); }
    to   { filter: drop-shadow(0 0 20px rgba(0,200,255,0.7)); }
}

.hero-sub {
    font-family: 'Rajdhani', sans-serif;
    font-size: 1.1rem;
    color: rgba(0,255,200,0.7);
    margin: 0.5rem 0 0 0;
    letter-spacing: 3px;
    text-transform: uppercase;
    position: relative;
    z-index: 1;
}

/* ── Neon metric cards ── */
.neon-card {
    background: linear-gradient(135deg, #0d1f35 0%, #0a1628 100%);
    border: 1px solid rgba(0,255,200,0.25);
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: all 0.3s ease;
    box-shadow: 0 0 20px rgba(0,255,200,0.05);
}

.neon-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #00ffc8, transparent);
    animation: scanLine 3s ease-in-out infinite;
}

@keyframes scanLine {
    0%   { transform: translateX(-100%); opacity: 0; }
    50%  { opacity: 1; }
    100% { transform: translateX(100%); opacity: 0; }
}

.neon-card:hover {
    border-color: rgba(0,255,200,0.6);
    box-shadow: 0 0 30px rgba(0,255,200,0.15), 0 0 60px rgba(0,255,200,0.05);
    transform: translateY(-3px);
}

.neon-value {
    font-family: 'Orbitron', monospace;
    font-size: 2.2rem;
    font-weight: 700;
    color: #00ffc8;
    text-shadow: 0 0 20px rgba(0,255,200,0.8);
    margin: 0;
}

.neon-label {
    font-size: 0.75rem;
    color: rgba(0,200,255,0.7);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-top: 0.5rem;
}

/* ── Bus timeline cards ── */
.bus-card {
    background: linear-gradient(135deg, #0d1f35 0%, #091525 100%);
    border: 1px solid rgba(0,150,255,0.2);
    border-left: 3px solid #00ffc8;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    margin: 0.5rem 0;
    transition: all 0.3s;
    box-shadow: 0 2px 15px rgba(0,0,0,0.3);
}

.bus-card:hover {
    border-color: rgba(0,255,200,0.5);
    box-shadow: 0 4px 25px rgba(0,255,200,0.1);
}

/* ── Info / status boxes ── */
.info-box {
    background: linear-gradient(135deg, #0d1f35 0%, #0a1628 100%);
    border: 1px solid rgba(0,150,255,0.3);
    border-left: 4px solid #00aaff;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin: 1rem 0;
    color: #c0d8f0;
}

.success-box {
    background: linear-gradient(135deg, #0a2010 0%, #071a0d 100%);
    border: 1px solid rgba(0,255,100,0.3);
    border-left: 4px solid #00ff64;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    color: #a0ffb0;
}

.warning-box {
    background: linear-gradient(135deg, #1f1200 0%, #180e00 100%);
    border: 1px solid rgba(255,160,0,0.3);
    border-left: 4px solid #ffa000;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    color: #ffd080;
}

/* ── Operator badge ── */
.op-badge {
    display: inline-block;
    background: linear-gradient(135deg, #00ffc8, #00aaff);
    color: #020b18;
    padding: 0.2rem 0.8rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #020b18 0%, #0a1628 100%) !important;
    border-right: 1px solid rgba(0,255,200,0.1) !important;
}

section[data-testid="stSidebar"] * {
    color: #c0d8f0 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    gap: 6px;
}

.stTabs [data-baseweb="tab"] {
    background: rgba(0,255,200,0.05) !important;
    border: 1px solid rgba(0,255,200,0.15) !important;
    border-radius: 8px 8px 0 0 !important;
    color: rgba(0,255,200,0.7) !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 1px !important;
    transition: all 0.3s !important;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,255,200,0.15), rgba(0,150,255,0.15)) !important;
    border-color: rgba(0,255,200,0.5) !important;
    color: #00ffc8 !important;
    box-shadow: 0 0 15px rgba(0,255,200,0.2) !important;
}

/* ── Button ── */
.stButton > button {
    background: linear-gradient(135deg, #00ffc8, #00aaff) !important;
    color: #020b18 !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Orbitron', monospace !important;
    font-weight: 900 !important;
    font-size: 0.9rem !important;
    letter-spacing: 2px !important;
    padding: 0.75rem 2rem !important;
    transition: all 0.3s !important;
    box-shadow: 0 0 20px rgba(0,255,200,0.3) !important;
    text-shadow: none !important;
    -webkit-text-fill-color: #020b18 !important;
}

.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 0 35px rgba(0,255,200,0.5) !important;
}

/* ── Selectbox / inputs ── */
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: #0d1f35 !important;
    border: 1px solid rgba(0,255,200,0.35) !important;
    border-radius: 8px !important;
    color: #00ffc8 !important;
}

/* Selectbox text */
.stSelectbox label, .stMultiSelect label, .stSlider label {
    color: #00ffc8 !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
    font-size: 0.8rem !important;
}

/* Dropdown selected value text */
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div,
.stMultiSelect [data-baseweb="select"] span,
.stMultiSelect [data-baseweb="select"] div {
    color: #c0d8f0 !important;
    background: transparent !important;
}

/* Dropdown popup menu */
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
    background: #0d1f35 !important;
    border: 1px solid rgba(0,255,200,0.3) !important;
    border-radius: 8px !important;
}

[data-baseweb="menu"] li,
[data-baseweb="option"] {
    background: #0d1f35 !important;
    color: #c0d8f0 !important;
}

[data-baseweb="menu"] li:hover,
[data-baseweb="option"]:hover {
    background: rgba(0,255,200,0.1) !important;
    color: #00ffc8 !important;
}

/* Multiselect tags */
[data-baseweb="tag"] {
    background: rgba(0,255,200,0.15) !important;
    border: 1px solid rgba(0,255,200,0.4) !important;
    color: #00ffc8 !important;
    border-radius: 20px !important;
}

/* Slider */
.stSlider [data-baseweb="slider"] div[role="slider"] {
    background: #00ffc8 !important;
    box-shadow: 0 0 10px rgba(0,255,200,0.6) !important;
}

.stSlider [data-baseweb="slider"] div[data-testid="stSliderTrackFill"] {
    background: linear-gradient(90deg, #00ffc8, #00aaff) !important;
}

/* ── Dataframe ── */
.stDataFrame {
    border: 1px solid rgba(0,255,200,0.2) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}

/* Dataframe table itself */
.stDataFrame table,
.stDataFrame thead,
.stDataFrame tbody,
.stDataFrame tr,
.stDataFrame th,
.stDataFrame td,
[data-testid="stDataFrame"] table,
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] td {
    background: #0a1628 !important;
    color: #c0d8f0 !important;
    border-color: rgba(0,255,200,0.1) !important;
    font-family: 'Rajdhani', sans-serif !important;
}

[data-testid="stDataFrame"] th {
    background: #0d1f35 !important;
    color: #00ffc8 !important;
    font-weight: 700 !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
    font-size: 0.8rem !important;
    border-bottom: 1px solid rgba(0,255,200,0.3) !important;
}

[data-testid="stDataFrame"] tr:hover td {
    background: rgba(0,255,200,0.05) !important;
}

/* iframe-based dataframe (Streamlit uses iframe for styled dataframes) */
.stDataFrame iframe {
    background: #0a1628 !important;
    border-radius: 8px !important;
}

/* ── Expander content background ── */
.streamlit-expanderContent {
    background: #091525 !important;
    border: 1px solid rgba(0,150,255,0.15) !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
}

/* ── Expander ── */
.streamlit-expanderHeader,
[data-testid="stExpander"] summary,
details summary {
    background: linear-gradient(135deg, #0d1f35, #091525) !important;
    border: 1px solid rgba(0,150,255,0.25) !important;
    border-radius: 8px !important;
    color: #00ffc8 !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    padding: 0.75rem 1rem !important;
}

[data-testid="stExpander"] summary:hover {
    border-color: rgba(0,255,200,0.5) !important;
    box-shadow: 0 0 15px rgba(0,255,200,0.1) !important;
}

[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
    color: #c0d8f0 !important;
}

/* ── General text ── */
h1, h2, h3, h4, h5, h6 {
    color: #c0d8f0 !important;
    font-family: 'Rajdhani', sans-serif !important;
}

p, li, label, .stMarkdown {
    color: #8ab0cc !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #00ffc8 !important;
}

/* ── Download button (secondary style) ── */
[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    color: #00ffc8 !important;
    border: 1px solid rgba(0,255,200,0.4) !important;
    border-radius: 6px !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 1px !important;
    padding: 0.4rem 1.2rem !important;
    transition: all 0.3s !important;
    box-shadow: none !important;
}

[data-testid="stDownloadButton"] > button:hover {
    background: rgba(0,255,200,0.1) !important;
    border-color: #00ffc8 !important;
    box-shadow: 0 0 15px rgba(0,255,200,0.2) !important;
    transform: translateY(-1px) !important;
}

/* ── Search input ── */
[data-testid="stTextInput"] input {
    background: #0d1f35 !important;
    border: 1px solid rgba(0,255,200,0.3) !important;
    border-radius: 8px !important;
    color: #c0d8f0 !important;
    font-family: 'Rajdhani', sans-serif !important;
}

[data-testid="stTextInput"] input:focus {
    border-color: #00ffc8 !important;
    box-shadow: 0 0 10px rgba(0,255,200,0.2) !important;
}

[data-testid="stTextInput"] label {
    color: #00ffc8 !important;
    font-size: 0.8rem !important;
    letter-spacing: 1px !important;
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #020b18; }
::-webkit-scrollbar-thumb { background: rgba(0,255,200,0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0,255,200,0.6); }

/* ── Pulse dot animation ── */
@keyframes pulseDot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(0.8); }
}

.live-dot {
    display: inline-block;
    width: 8px; height: 8px;
    background: #00ffc8;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulseDot 1.5s ease-in-out infinite;
    box-shadow: 0 0 8px #00ffc8;
}

/* ── Route path visual ── */
.route-path {
    display: flex;
    align-items: center;
    gap: 0;
    flex-wrap: wrap;
    padding: 1rem 0;
}

.route-node {
    background: linear-gradient(135deg, #00ffc8, #00aaff);
    color: #020b18;
    padding: 0.4rem 1rem;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.85rem;
    letter-spacing: 1px;
    white-space: nowrap;
}

.route-node.station {
    background: linear-gradient(135deg, #7b2fff, #00aaff);
    color: white;
    box-shadow: 0 0 15px rgba(123,47,255,0.4);
}

.route-arrow {
    color: rgba(0,255,200,0.5);
    font-size: 1.2rem;
    padding: 0 0.3rem;
    animation: arrowPulse 2s ease-in-out infinite;
}

@keyframes arrowPulse {
    0%, 100% { opacity: 0.3; }
    50%       { opacity: 1; color: #00ffc8; }
}

/* ── Charging progress bar ── */
.charge-bar-wrap {
    background: rgba(0,255,200,0.08);
    border-radius: 4px;
    height: 6px;
    margin-top: 6px;
    overflow: hidden;
}

.charge-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #00ffc8, #00aaff);
    border-radius: 4px;
    animation: chargeAnim 2s ease-in-out infinite alternate;
}

@keyframes chargeAnim {
    from { opacity: 0.6; }
    to   { opacity: 1; box-shadow: 0 0 8px #00ffc8; }
}
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Helper Functions
# ============================================================================

def load_scenarios() -> Dict[str, Path]:
    scenarios_dir = Path("scenarios")
    scenario_files = {}
    if scenarios_dir.exists():
        for file_path in sorted(scenarios_dir.glob("*.json")):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    scenario_name = data.get("name", file_path.stem)
                    scenario_files[scenario_name] = file_path
            except Exception as e:
                st.sidebar.error(f"Error loading {file_path.name}: {e}")
    return scenario_files


def load_scenario(file_path: Path) -> Optional[Scenario]:
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return Scenario(**data)
    except Exception as e:
        st.error(f"Error loading scenario: {e}")
        return None


def format_time(time_str: str) -> str:
    try:
        return time_str[:5] if len(time_str) > 5 else time_str
    except:
        return time_str


def calculate_summary_stats(result: SimulationResult, scenario: Scenario) -> Dict:
    if not result.bus_timelines:
        return {"total_wait": 0, "max_wait": 0, "avg_wait": 0, "operator_stats": {}}

    wait_times = [t.total_wait_minutes for t in result.bus_timelines.values()]
    total_wait = sum(wait_times)
    max_wait = max(wait_times) if wait_times else 0
    avg_wait = total_wait / len(wait_times) if wait_times else 0

    operator_waits: Dict[str, List[int]] = {}
    for timeline in result.bus_timelines.values():
        operator_waits.setdefault(timeline.operator, []).append(timeline.total_wait_minutes)

    operator_stats = {
        op: {
            "total_wait": sum(w),
            "avg_wait": sum(w) / len(w),
            "max_wait": max(w),
            "num_buses": len(w)
        }
        for op, w in operator_waits.items()
    }

    return {"total_wait": total_wait, "max_wait": max_wait, "avg_wait": avg_wait, "operator_stats": operator_stats}


# ============================================================================
# Visualization Functions (dark-themed Plotly)
# ============================================================================

DARK_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(13,31,53,0.6)',
    font=dict(color='#8ab0cc', family='Rajdhani, sans-serif'),
    xaxis=dict(gridcolor='rgba(0,255,200,0.07)', zerolinecolor='rgba(0,255,200,0.1)'),
    yaxis=dict(gridcolor='rgba(0,255,200,0.07)', zerolinecolor='rgba(0,255,200,0.1)'),
)

NEON_COLORS = ['#00ffc8', '#00aaff', '#7b2fff', '#ff6b6b', '#ffa500', '#ff00aa']


def create_timeline_chart(result: SimulationResult, scenario: Scenario):
    """Simple stacked bar: travel time vs wait time per bus."""
    data = []
    for bus_id, t in sorted(result.bus_timelines.items()):
        dep = datetime.strptime(t.departure_time, "%H:%M")
        arr = datetime.strptime(t.arrival_time, "%H:%M")
        if arr < dep:
            arr = arr.replace(day=dep.day + 1)
        total_min = int((arr - dep).total_seconds() / 60)
        travel_min = total_min - t.total_wait_minutes
        data.append({"Bus": bus_id, "Operator": t.operator,
                     "Travel Time": travel_min, "Wait Time": t.total_wait_minutes})

    df = pd.DataFrame(data)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Travel Time",
        y=df["Bus"], x=df["Travel Time"],
        orientation='h',
        marker_color='#00aaff',
        hovertemplate="%{y}<br>Travel: %{x} min<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        name="Wait Time",
        y=df["Bus"], x=df["Wait Time"],
        orientation='h',
        marker_color='#ff6b6b',
        hovertemplate="%{y}<br>Wait: %{x} min<extra></extra>"
    ))
    fig.update_layout(
        barmode='stack',
        title=dict(text="🚌 Travel vs Wait Time per Bus", font=dict(color='#00ffc8', size=15)),
        height=max(350, len(data) * 28 + 80),
        xaxis=dict(title="Minutes", tickfont=dict(color='#8ab0cc'),
                   gridcolor='rgba(0,255,200,0.07)'),
        yaxis=dict(tickfont=dict(color='#8ab0cc', size=10)),
        legend=dict(font=dict(color='#8ab0cc'), bgcolor='rgba(13,31,53,0.8)',
                    bordercolor='rgba(0,255,200,0.2)', borderwidth=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(13,31,53,0.5)',
        font=dict(color='#8ab0cc', family='Rajdhani, sans-serif'),
        margin=dict(l=120, r=20, t=50, b=40),
    )
    return fig


def create_station_heatmap(result: SimulationResult, scenario: Scenario):
    """Simple bar: how many buses charged at each station."""
    data = []
    for sid, queue in result.station_queues.items():
        name = next((s.name for s in scenario.route.stations if s.id == sid), sid)
        total_wait = sum(
            max(0, int((datetime.strptime(e.charge_start, "%H:%M") -
                        datetime.strptime(e.arrival_time, "%H:%M")).total_seconds() / 60))
            for e in queue
        )
        data.append({"Station": name, "Buses": len(queue), "Total Wait (min)": total_wait})

    df = pd.DataFrame(data)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Buses Charged",
        x=df["Station"], y=df["Buses"],
        marker_color='#00ffc8',
        text=df["Buses"], textposition='outside',
        textfont=dict(color='#00ffc8'),
        hovertemplate="%{x}<br>Buses: %{y}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        name="Total Wait (min)",
        x=df["Station"], y=df["Total Wait (min)"],
        marker_color='#ffa500',
        text=df["Total Wait (min)"], textposition='outside',
        textfont=dict(color='#ffa500'),
        hovertemplate="%{x}<br>Total Wait: %{y} min<extra></extra>"
    ))
    fig.update_layout(
        barmode='group',
        title=dict(text="🔌 Station Load", font=dict(color='#00ffc8', size=15)),
        height=320,
        xaxis=dict(tickfont=dict(color='#8ab0cc', size=12)),
        yaxis=dict(tickfont=dict(color='#8ab0cc'), gridcolor='rgba(0,255,200,0.07)'),
        legend=dict(font=dict(color='#8ab0cc'), bgcolor='rgba(13,31,53,0.8)',
                    bordercolor='rgba(0,255,200,0.2)', borderwidth=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(13,31,53,0.5)',
        font=dict(color='#8ab0cc', family='Rajdhani, sans-serif'),
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def create_wait_time_chart(result: SimulationResult, scenario: Scenario):
    data = [{"Bus ID": bid, "Operator": t.operator, "Wait Time (min)": t.total_wait_minutes}
            for bid, t in sorted(result.bus_timelines.items())]
    df = pd.DataFrame(data)
    fig = px.bar(df, x="Bus ID", y="Wait Time (min)", color="Operator",
                 title="🕐 Wait Time by Bus", text="Wait Time (min)",
                 color_discrete_sequence=NEON_COLORS)
    fig.update_traces(textposition='outside', marker_line_width=0)
    fig.update_layout(height=400, title_font=dict(color='#00ffc8', size=16), **DARK_LAYOUT)
    return fig


def create_operator_comparison(result: SimulationResult, scenario: Scenario):
    stats = calculate_summary_stats(result, scenario)
    if not stats['operator_stats']:
        return None
    operators, avg_waits, max_waits = [], [], []
    for op, s in stats['operator_stats'].items():
        operators.append(op.upper())
        avg_waits.append(s['avg_wait'])
        max_waits.append(s['max_wait'])
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Avg Wait Time', 'Max Wait Time'))
    fig.add_trace(go.Bar(x=operators, y=avg_waits, name="Avg", marker_color='#00ffc8',
                         marker_line_width=0), row=1, col=1)
    fig.add_trace(go.Bar(x=operators, y=max_waits, name="Max", marker_color='#7b2fff',
                         marker_line_width=0), row=1, col=2)
    fig.update_layout(height=380, showlegend=False,
                      title_text="👥 Operator Fairness",
                      title_font=dict(color='#00ffc8', size=16),
                      paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(13,31,53,0.6)',
                      font=dict(color='#8ab0cc', family='Rajdhani, sans-serif'))
    fig.update_annotations(font_color='#8ab0cc')
    return fig


def create_station_utilization(result: SimulationResult, scenario: Scenario):
    station_data = []
    for sid, queue in result.station_queues.items():
        name = next((s.name for s in scenario.route.stations if s.id == sid), sid)
        total_wait = 0
        for entry in queue:
            try:
                arr = datetime.strptime(entry.arrival_time, "%H:%M")
                cs = datetime.strptime(entry.charge_start, "%H:%M")
                w = int((cs - arr).total_seconds() / 60)
                total_wait += w if w >= 0 else w + 24 * 60
            except:
                pass
        station_data.append({"Station": name, "Buses Charged": len(queue), "Total Wait": total_wait})
    df = pd.DataFrame(station_data)
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Buses Charged', 'Total Wait (min)'))
    fig.add_trace(go.Bar(x=df["Station"], y=df["Buses Charged"], marker_color='#00ffc8',
                         marker_line_width=0), row=1, col=1)
    fig.add_trace(go.Bar(x=df["Station"], y=df["Total Wait"], marker_color='#ff6b6b',
                         marker_line_width=0), row=1, col=2)
    fig.update_layout(height=380, showlegend=False,
                      title_text="🔌 Station Utilization",
                      title_font=dict(color='#00ffc8', size=16),
                      paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(13,31,53,0.6)',
                      font=dict(color='#8ab0cc', family='Rajdhani, sans-serif'))
    fig.update_annotations(font_color='#8ab0cc')
    return fig


# ============================================================================
# Main Application
# ============================================================================

def main():
    # ── Hero Header ──────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero-header">
        <div class="hero-title">⚡ EV BUS CHARGING SCHEDULER</div>
        <div class="hero-sub">
            <span class="live-dot"></span>
            Intelligent Multi-Objective Optimization · Real-Time Simulation
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    st.sidebar.markdown("""
    <div style="text-align:center; padding: 1rem 0;">
        <div style="font-family:'Orbitron',monospace; font-size:1rem; color:#00ffc8;
                    letter-spacing:3px; text-shadow: 0 0 10px rgba(0,255,200,0.5);">
            CONTROL PANEL
        </div>
    </div>
    """, unsafe_allow_html=True)

    scenario_files = load_scenarios()
    if not scenario_files:
        st.error("No scenario files found in the scenarios/ directory.")
        return

    selected_scenario_name = st.sidebar.selectbox(
        "Select Scenario",
        list(scenario_files.keys()),
        help="Choose a scenario to load"
    )

    selected_file = scenario_files[selected_scenario_name]
    scenario = load_scenario(selected_file)
    if scenario is None:
        st.error("Failed to load scenario.")
        return

    st.sidebar.markdown("---")

    # Sidebar: show weights
    st.sidebar.markdown("**⚖️ Objective Weights**")
    st.sidebar.markdown(f"""
    <div style="font-size:0.85rem; color:#8ab0cc; line-height:2;">
        Individual &nbsp;&nbsp; <span style="color:#00ffc8; font-weight:700;">{scenario.weights.individual}</span><br>
        Operator &nbsp;&nbsp;&nbsp;&nbsp; <span style="color:#00aaff; font-weight:700;">{scenario.weights.operator}</span><br>
        Overall &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:#7b2fff; font-weight:700;">{scenario.weights.overall}</span>
    </div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("---")
    run_button = st.sidebar.button("▶  RUN SCHEDULER", type="primary", use_container_width=True)

    # Session state
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'current_scenario' not in st.session_state:
        st.session_state.current_scenario = None
    if st.session_state.current_scenario != selected_scenario_name:
        st.session_state.result = None
        st.session_state.current_scenario = selected_scenario_name

    if run_button:
        with st.spinner("Running scheduler..."):
            try:
                scheduler = BusScheduler(scenario)
                st.session_state.result = scheduler.schedule()
                st.sidebar.success("✅ Done!")
            except Exception as e:
                st.sidebar.error(f"❌ Failed: {e}")
                st.session_state.result = None

    result = st.session_state.result

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["⚙️  SCENARIO CONFIG", "🚌  BUS TIMELINES", "🔌  STATION QUEUES"])

    # ── Tab 1: Scenario Config ────────────────────────────────────────────────
    with tab1:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"""
            <div class="info-box">
                <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.9rem;
                            letter-spacing:2px; margin-bottom:0.8rem;">PARAMETERS</div>
                🔋 Battery Capacity: <strong style="color:#00ffc8;">{scenario.parameters.battery_capacity_km} km</strong><br>
                ⚡ Charge Duration: <strong style="color:#00ffc8;">{scenario.parameters.charge_duration_minutes} min</strong><br>
                🚀 Speed: <strong style="color:#00ffc8;">{scenario.parameters.speed_kmh} km/h</strong>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="info-box">
                <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.9rem;
                            letter-spacing:2px; margin-bottom:0.8rem;">OBJECTIVE WEIGHTS</div>
                👤 Individual: <strong style="color:#00ffc8;">{scenario.weights.individual}</strong><br>
                👥 Operator: <strong style="color:#00aaff;">{scenario.weights.operator}</strong><br>
                🌐 Overall: <strong style="color:#7b2fff;">{scenario.weights.overall}</strong>
            </div>
            """, unsafe_allow_html=True)

        # Route visual
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.85rem;
                    letter-spacing:2px; margin: 1.5rem 0 0.5rem 0;">ROUTE</div>
        """, unsafe_allow_html=True)

        route_html = f'<div class="route-path"><span class="route-node">{scenario.route.origin}</span>'
        for seg in scenario.route.segments:
            is_station = any(s.id == seg.to_location or s.name == seg.to_location
                             for s in scenario.route.stations)
            node_class = "route-node station" if is_station else "route-node"
            route_html += f'<span class="route-arrow">──{seg.distance_km}km──▶</span>'
            route_html += f'<span class="{node_class}">{seg.to_location}</span>'
        route_html += '</div>'
        st.markdown(route_html, unsafe_allow_html=True)

        # Stations table
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.85rem;
                    letter-spacing:2px; margin: 1.5rem 0 0.5rem 0;">CHARGING STATIONS</div>
        """, unsafe_allow_html=True)
        station_rows = [{"ID": s.id, "Name": s.name, "Chargers": s.num_chargers}
                        for s in scenario.route.stations]
        show_table(station_rows, key="stations")

        # Bus schedule
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.85rem;
                    letter-spacing:2px; margin: 1.5rem 0 0.5rem 0;">BUS SCHEDULE</div>
        """, unsafe_allow_html=True)
        bus_data = [{"Bus ID": b.id, "Operator": b.operator,
                     "Direction": f"{b.origin} → {b.destination}",
                     "Departure": format_time(b.departure_time)}
                    for b in scenario.buses]
        show_table(bus_data, key="buses", search=True)

    # ── No results yet ────────────────────────────────────────────────────────
    if result is None:
        with tab2:
            st.markdown("""
            <div class="info-box" style="text-align:center; padding:3rem;">
                <div style="font-size:3rem;">⚡</div>
                <div style="font-family:'Orbitron',monospace; color:#00ffc8; margin-top:1rem;">
                    AWAITING SCHEDULER EXECUTION
                </div>
                <div style="color:#8ab0cc; margin-top:0.5rem;">
                    Click RUN SCHEDULER in the sidebar to generate the charging plan
                </div>
            </div>
            """, unsafe_allow_html=True)
        with tab3:
            st.markdown("""
            <div class="info-box" style="text-align:center; padding:3rem;">
                <div style="font-size:3rem;">🔌</div>
                <div style="font-family:'Orbitron',monospace; color:#00ffc8; margin-top:1rem;">
                    NO DATA YET
                </div>
            </div>
            """, unsafe_allow_html=True)
        return

    # ── Tab 2: Bus Timelines ──────────────────────────────────────────────────
    with tab2:
        stats = calculate_summary_stats(result, scenario)

        # Metric cards
        c1, c2, c3, c4 = st.columns(4)
        cards = [
            (stats['total_wait'], "TOTAL WAIT", "min"),
            (stats['max_wait'], "MAX WAIT", "min"),
            (f"{stats['avg_wait']:.1f}", "AVG WAIT", "min"),
            (len(result.bus_timelines), "BUSES", "scheduled"),
        ]
        for col, (val, label, unit) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"""
                <div class="neon-card">
                    <div class="neon-value">{val}</div>
                    <div class="neon-label">{label} ({unit})</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Charts row
        col1, col2 = st.columns(2)
        with col1:
            fig = create_wait_time_chart(result, scenario)
            if fig: st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = create_operator_comparison(result, scenario)
            if fig: st.plotly_chart(fig, use_container_width=True)

        # Timeline + Heatmap
        col_tl, col_hm = st.columns([3, 2])
        with col_tl:
            fig = create_timeline_chart(result, scenario)
            if fig: st.plotly_chart(fig, use_container_width=True)
        with col_hm:
            fig = create_station_heatmap(result, scenario)
            if fig: st.plotly_chart(fig, use_container_width=True)

        # Operator stats
        if stats['operator_stats']:
            st.markdown("""
            <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.85rem;
                        letter-spacing:2px; margin: 1.5rem 0 0.5rem 0;">OPERATOR PERFORMANCE</div>
            """, unsafe_allow_html=True)
            op_cols = st.columns(len(stats['operator_stats']))
            for idx, (op, s) in enumerate(stats['operator_stats'].items()):
                with op_cols[idx]:
                    st.markdown(f"""
                    <div class="neon-card">
                        <div style="font-family:'Orbitron',monospace; color:#00ffc8;
                                    font-size:1rem; margin-bottom:0.8rem;">{op.upper()}</div>
                        <div style="color:#8ab0cc; font-size:0.85rem; line-height:2;">
                            Buses: <strong style="color:#00ffc8;">{s['num_buses']}</strong><br>
                            Total Wait: <strong style="color:#ffa500;">{s['total_wait']} min</strong><br>
                            Avg Wait: <strong style="color:#00aaff;">{s['avg_wait']:.1f} min</strong><br>
                            Max Wait: <strong style="color:#ff6b6b;">{s['max_wait']} min</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # Detailed timelines
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:0.85rem;
                    letter-spacing:2px; margin: 2rem 0 0.5rem 0;">DETAILED BUS TIMELINES</div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            all_ops = sorted(set(t.operator for t in result.bus_timelines.values()))
            sel_ops = st.multiselect("Filter by Operator", all_ops, default=all_ops)
        with col2:
            sort_opt = st.selectbox("Sort by", ["Bus ID", "Departure Time",
                                                 "Wait Time (Low→High)", "Wait Time (High→Low)", "Arrival Time"])
        with col3:
            max_w = max((t.total_wait_minutes for t in result.bus_timelines.values()), default=0)
            wait_filter = st.slider("Max Wait (min)", 0, max(max_w, 1), max(max_w, 1)) if max_w > 0 else 0

        filtered = {bid: t for bid, t in result.bus_timelines.items()
                    if t.operator in sel_ops and t.total_wait_minutes <= wait_filter}

        sort_keys = {
            "Bus ID": lambda x: x[0],
            "Departure Time": lambda x: x[1].departure_time,
            "Wait Time (Low→High)": lambda x: x[1].total_wait_minutes,
            "Wait Time (High→Low)": lambda x: -x[1].total_wait_minutes,
            "Arrival Time": lambda x: x[1].arrival_time,
        }
        sorted_timelines = sorted(filtered.items(), key=sort_keys.get(sort_opt, lambda x: x[0]))

        if len(filtered) < len(result.bus_timelines):
            st.info(f"Showing {len(filtered)} of {len(result.bus_timelines)} buses")

        for bus_id, timeline in sorted_timelines:
            wait_color = "#00ff64" if timeline.total_wait_minutes == 0 else \
                         "#ffa500" if timeline.total_wait_minutes < 10 else "#ff6b6b"
            with st.expander(
                f"🚌 {timeline.bus_id}  ·  {timeline.operator.upper()}  ·  "
                f"Dep {format_time(timeline.departure_time)}  →  Arr {format_time(timeline.arrival_time)}  ·  "
                f"Wait: {timeline.total_wait_minutes} min",
                expanded=False
            ):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"""
                    <div class="bus-card">
                        <span style="color:#8ab0cc;">Direction:</span>
                        <strong style="color:#c0d8f0;"> {timeline.direction}</strong><br>
                        <span style="color:#8ab0cc;">Departure:</span>
                        <strong style="color:#00ffc8;"> {format_time(timeline.departure_time)}</strong>
                        &nbsp;&nbsp;
                        <span style="color:#8ab0cc;">Arrival:</span>
                        <strong style="color:#00ffc8;"> {format_time(timeline.arrival_time)}</strong><br>
                        <span style="color:#8ab0cc;">Total Wait:</span>
                        <strong style="color:{wait_color};"> {timeline.total_wait_minutes} min</strong>
                        <div class="charge-bar-wrap">
                            <div class="charge-bar-fill" style="width:{min(100, timeline.total_wait_minutes * 2)}%;"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with c2:
                    st.markdown(f"""
                    <div class="neon-card" style="padding:1rem;">
                        <div class="neon-value" style="font-size:1.8rem;">{len(timeline.charging_stops)}</div>
                        <div class="neon-label">STOPS</div>
                    </div>
                    """, unsafe_allow_html=True)

                if timeline.charging_stops:
                    stop_data = [{"Station": s.station, "Arrival": format_time(s.arrival_time),
                                  "Wait (min)": s.wait_minutes, "Charge Start": format_time(s.charge_start),
                                  "Charge End": format_time(s.charge_end)}
                                 for s in timeline.charging_stops]
                    show_table(stop_data, highlight_col="Wait (min)", highlight_val=0,
                               key=f"stops_{bus_id}")
                else:
                    st.markdown('<div class="success-box">✅ No charging stops needed.</div>',
                                unsafe_allow_html=True)

    # ── Tab 3: Station Queues ─────────────────────────────────────────────────
    with tab3:
        fig = create_station_utilization(result, scenario)
        if fig: st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        station_ids = sorted(result.station_queues.keys())
        if not station_ids:
            st.info("No station queue data available.")
            return

        station_tabs = st.tabs([f"⚡ Station {sid}" for sid in station_ids])

        for idx, station_id in enumerate(station_ids):
            with station_tabs[idx]:
                queue = result.station_queues[station_id]
                station_name = next((s.name for s in scenario.route.stations if s.id == station_id), station_id)

                total_wait = 0
                buses_with_wait = 0
                queue_data = []

                for entry in queue:
                    try:
                        arr = datetime.strptime(entry.arrival_time, "%H:%M")
                        cs = datetime.strptime(entry.charge_start, "%H:%M")
                        w = int((cs - arr).total_seconds() / 60)
                        if w < 0: w += 24 * 60
                    except:
                        w = 0
                    if w > 0:
                        buses_with_wait += 1
                        total_wait += w
                    queue_data.append({"Bus ID": entry.bus_id, "Arrival": format_time(entry.arrival_time),
                                       "Wait (min)": w, "Charge Start": format_time(entry.charge_start),
                                       "Charge End": format_time(entry.charge_end)})

                st.markdown(f"""
                <div style="font-family:'Orbitron',monospace; color:#00ffc8; font-size:1.1rem;
                            letter-spacing:3px; margin-bottom:1rem;
                            text-shadow: 0 0 15px rgba(0,255,200,0.5);">
                    ⚡ {station_name.upper()}
                </div>
                """, unsafe_allow_html=True)

                c1, c2, c3 = st.columns(3)
                for col, (val, label) in zip([c1, c2, c3], [
                    (len(queue), "BUSES CHARGED"),
                    (buses_with_wait, "BUSES WITH WAIT"),
                    (total_wait, "TOTAL WAIT (MIN)")
                ]):
                    with col:
                        st.markdown(f"""
                        <div class="neon-card">
                            <div class="neon-value">{val}</div>
                            <div class="neon-label">{label}</div>
                        </div>
                        """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                if not queue:
                    st.info(f"No buses charged at {station_name}.")
                    continue

                show_table(queue_data, highlight_col="Wait (min)", highlight_val=0,
                           key=f"queue_{station_id}", search=True)

                if buses_with_wait > 0:
                    st.markdown(f"""
                    <div class="warning-box">
                        ⚠️ <strong>{buses_with_wait} bus(es)</strong> experienced wait time at this station.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="success-box">
                        ✅ <strong>No wait times!</strong> All buses charged immediately.
                    </div>
                    """, unsafe_allow_html=True)


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    main()
