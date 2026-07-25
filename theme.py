# theme.py
# ==============================================================================
# THEME PARTAGE — 3 palettes prédéfinies + palette personnalisée
# Sélecteur intégré dans la sidebar, persistant via st.session_state.
# ==============================================================================
import streamlit as st

PALETTES = {
    "bloomberg": {
        "label": "Bloomberg terminal",
        "bg": "#0a0a0a",
        "card": "#161616",
        "border": "#262626",
        "accent": "#ff9f0a",
        "text": "#e8e8e8",
        "text_muted": "#999999",
        "up": "#00d964",
        "down": "#ff3b30",
    },
    "nuit": {
        "label": "Nuit financière",
        "bg": "#0b1120",
        "card": "#141d33",
        "border": "#1c2941",
        "accent": "#f5a623",
        "text": "#dce6f5",
        "text_muted": "#94a8c7",
        "up": "#3ddc84",
        "down": "#ff5c7a",
    },
    "obsidienne": {
        "label": "Obsidienne quant",
        "bg": "#0d0d14",
        "card": "#171723",
        "border": "#20202e",
        "accent": "#00e5cc",
        "text": "#c4c4d4",
        "text_muted": "#8d8da3",
        "up": "#5ee6a8",
        "down": "#ff5c7a",
    },
}

DEFAULT_CUSTOM = {
    "label": "Personnalisée",
    "bg": "#0f172a",
    "card": "#1e293b",
    "border": "#334155",
    "accent": "#f59e0b",
    "text": "#f8fafc",
    "text_muted": "#94a3b8",
    "up": "#22c55e",
    "down": "#ef4444",
}


def _init_state():
    if "thesee_palette_id" not in st.session_state:
        st.session_state["thesee_palette_id"] = "nuit"
    if "thesee_custom_palette" not in st.session_state:
        st.session_state["thesee_custom_palette"] = dict(DEFAULT_CUSTOM)


def get_active_palette() -> dict:
    """Retourne le dict de couleurs actif (prédéfini ou personnalisé)."""
    _init_state()
    pid = st.session_state["thesee_palette_id"]
    if pid == "custom":
        return st.session_state["thesee_custom_palette"]
    return PALETTES[pid]


def palette_selector_sidebar():
    """
    Sélecteur de palette à placer dans la sidebar de chaque page.
    Persistant via st.session_state -> le choix fait sur une page s'applique
    à toutes les autres pages de la session (Streamlit partage le session_state
    entre toutes les pages d'une même session utilisateur).
    """
    _init_state()
    st.markdown("**Thème visuel**")

    options = list(PALETTES.keys()) + ["custom"]
    labels = {k: v["label"] for k, v in PALETTES.items()}
    labels["custom"] = "Personnalisée"

    choix = st.radio(
        "Palette",
        options=options,
        format_func=lambda k: labels[k],
        index=options.index(st.session_state["thesee_palette_id"]),
        key="thesee_palette_radio",
        label_visibility="collapsed",
    )
    st.session_state["thesee_palette_id"] = choix

    if choix == "custom":
        with st.expander("Personnaliser les couleurs", expanded=True):
            custom = st.session_state["thesee_custom_palette"]
            custom["bg"] = st.color_picker("Fond principal", custom["bg"])
            custom["card"] = st.color_picker("Fond carte", custom["card"])
            custom["accent"] = st.color_picker("Accent", custom["accent"])
            custom["text"] = st.color_picker("Texte", custom["text"])
            custom["up"] = st.color_picker("Hausse", custom["up"])
            custom["down"] = st.color_picker("Baisse", custom["down"])
            custom["border"] = custom["bg"]
            custom["text_muted"] = custom["text"]
            st.session_state["thesee_custom_palette"] = custom

    p = get_active_palette()
    st.markdown(
        f"""
        <div style="background:{p['bg']};border:1px solid {p['border']};
                    border-radius:8px;padding:8px;margin-top:8px;">
            <div style="background:{p['card']};border-radius:6px;padding:8px;">
                <span style="color:{p['text_muted']};font-size:11px;">Aperçu</span><br>
                <span style="color:{p['accent']};font-size:16px;font-weight:600;">54.2%</span>
                <span style="color:{p['up']};font-size:12px;margin-left:8px;">+2.1%</span>
                <span style="color:{p['down']};font-size:12px;margin-left:6px;">-1.4%</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_css(p: dict) -> str:
    return f"""
    <style>
    .stApp {{ background-color: {p['bg']}; color: {p['text']}; }}

    [data-testid="stSidebar"] {{
        background-color: {p['card']};
        border-right: 1px solid {p['border']};
    }}

    h1, h2, h3, h4, h5 {{ color: {p['accent']} !important; }}

    div[data-testid="stMetric"] {{
        background-color: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 12px;
    }}
    div[data-testid="stMetricLabel"] {{ color: {p['text_muted']} !important; }}
    div[data-testid="stMetricValue"] {{ color: {p['text']} !important; }}

    .stButton button {{
        background-color: {p['accent']};
        color: {p['bg']};
        border: none;
        font-weight: 600;
        border-radius: 6px;
    }}
    .stButton button:hover {{ opacity: 0.85; }}

    div[data-testid="stDataFrame"] {{
        border: 1px solid {p['border']};
        border-radius: 8px;
    }}

    .stProgress > div > div {{ background-color: {p['accent']}; }}

    @media (max-width: 768px) {{
        .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        div[data-testid="stMetric"] {{ margin-bottom: 8px; }}
    }}
    </style>
    """


def apply_theme():
    """À appeler en haut de chaque page (après st.set_page_config)."""
    p = get_active_palette()
    st.markdown(build_css(p), unsafe_allow_html=True)
