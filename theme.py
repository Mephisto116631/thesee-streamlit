# theme.py
# ==============================================================================
# THEME PARTAGE — Ardoise / Orange (porte depuis utils.py R-Shiny)
# ==============================================================================
import streamlit as st

CSS_GLOBAL = """
<style>
.stApp { background-color: #0f172a; color: #f8fafc; }

[data-testid="stSidebar"] {
    background-color: #0b1120;
    border-right: 1px solid #475569;
}

[data-testid="stSidebar"] * {
    color: #f1f5f9 !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #fbbf24 !important;
}

[data-testid="stSidebar"] label {
    color: #e2e8f0 !important;
    font-weight: 500;
}

h1, h2, h3, h4, h5 { color: #fbbf24 !important; }

div[data-testid="stMetric"] {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px;
}

.stButton button {
    background-color: #3b82f6;
    color: white;
    border: none;
    font-weight: 600;
    border-radius: 6px;
}
.stButton button:hover { background-color: #2563eb; }

div[data-testid="stDataFrame"] { border: 1px solid #334155; border-radius: 8px; }

/* Responsive : empile les colonnes sous 768px (comportement natif Streamlit,
   on ajuste juste les marges pour eviter le sur-tassement) */
@media (max-width: 768px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    div[data-testid="stMetric"] { margin-bottom: 8px; }
}
</style>
"""


def apply_theme():
    st.markdown(CSS_GLOBAL, unsafe_allow_html=True)