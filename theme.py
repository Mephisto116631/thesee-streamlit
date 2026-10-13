# theme.py
# ==============================================================================
# THEME PARTAGE — palettes + CSS. Conçu pour de longues sessions de travail :
# - une seule couleur d'accent, réservée à ce qui est interactif ou sélectionné
# - hiérarchie par taille et graisse, pas par la couleur
# - chiffres tabulaires (colonnes alignées), contrastes ≥ 4,5:1
# Le thème sombre de base est imposé par .streamlit/config.toml (tableaux, champs).
# ==============================================================================
import streamlit as st


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1: str, c2: str, t: float) -> str:
    """Mélange c1 -> c2 (t=0 : c1, t=1 : c2)."""
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


PALETTES = {
    "nuit": {
        "label": "Nuit financière",
        "bg": "#11151c", "card": "#1a2029", "border": "#29313d",
        "accent": "#e3a63b", "text": "#e6e9ef", "text_muted": "#9aa5b5",
        "up": "#3fcf8e", "down": "#ff6b7d",
    },
    "bloomberg": {
        "label": "Bloomberg terminal",
        "bg": "#0e0e0e", "card": "#181818", "border": "#2a2a2a",
        "accent": "#ff9f0a", "text": "#ebebeb", "text_muted": "#a0a0a0",
        "up": "#2fd573", "down": "#ff453a",
    },
    "obsidienne": {
        "label": "Obsidienne quant",
        "bg": "#0f0f17", "card": "#191925", "border": "#2a2a3a",
        "accent": "#2dd4bf", "text": "#e4e4ee", "text_muted": "#9a9ab0",
        "up": "#5ee6a8", "down": "#ff6b7d",
    },
}

DEFAULT_CUSTOM = {
    "label": "Personnalisée",
    "bg": "#11151c", "card": "#1a2029", "border": "#29313d",
    "accent": "#e3a63b", "text": "#e6e9ef", "text_muted": "#9aa5b5",
    "up": "#3fcf8e", "down": "#ff6b7d",
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
    """Sélecteur de palette (sidebar). Le choix est partagé entre les pages via session_state."""
    _init_state()
    options = list(PALETTES.keys()) + ["custom"]
    labels = {k: v["label"] for k, v in PALETTES.items()}
    labels["custom"] = "Personnalisée"

    choix = st.selectbox(
        "Thème visuel",
        options=options,
        format_func=lambda k: labels[k],
        index=options.index(st.session_state["thesee_palette_id"]),
        key="thesee_palette_select",
    )
    st.session_state["thesee_palette_id"] = choix

    if choix == "custom":
        with st.expander("Couleurs", expanded=True):
            c = st.session_state["thesee_custom_palette"]
            c["bg"] = st.color_picker("Fond", c["bg"])
            c["accent"] = st.color_picker("Accent", c["accent"])
            c["text"] = st.color_picker("Texte", c["text"])
            c["up"] = st.color_picker("Hausse", c["up"])
            c["down"] = st.color_picker("Baisse", c["down"])
            # Surfaces, bordures et texte secondaire dérivés du fond et du texte :
            # garantit des contrastes cohérents quelles que soient les couleurs choisies.
            c["card"] = _mix(c["bg"], c["text"], 0.07)
            c["border"] = _mix(c["bg"], c["text"], 0.17)
            c["text_muted"] = _mix(c["bg"], c["text"], 0.65)
            st.session_state["thesee_custom_palette"] = c


def build_css(p: dict) -> str:
    surface2 = _mix(p["bg"], p["text"], 0.11)
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    :root {{
        --t-bg: {p['bg']}; --t-card: {p['card']}; --t-card2: {surface2};
        --t-border: {p['border']}; --t-accent: {p['accent']};
        --t-text: {p['text']}; --t-muted: {p['text_muted']};
        --t-up: {p['up']}; --t-down: {p['down']};
    }}

    html, body, .stApp, [data-testid="stAppViewContainer"] {{
        font-family: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
        font-variant-numeric: tabular-nums;
    }}
    .stApp {{ background-color: var(--t-bg); color: var(--t-text); }}
    [data-testid="stHeader"] {{ background: transparent; }}
    #MainMenu, footer {{ visibility: hidden; }}

    /* --- Mise en page : largeur de lecture bornée sur grand écran --- */
    .block-container {{
        padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1480px;
    }}

    /* --- Titres : la hiérarchie vient de la taille et du poids, pas de la couleur --- */
    h1 {{ font-size: 1.75rem !important; font-weight: 600 !important; letter-spacing: -0.01em;
          color: var(--t-text) !important; padding-bottom: .4rem; }}
    h2, h3 {{ color: var(--t-text) !important; font-weight: 600 !important; letter-spacing: -0.005em; }}
    h2 {{ font-size: 1.3rem !important; }}
    h3 {{ font-size: 1.1rem !important; padding-bottom: .35rem; border-bottom: 1px solid var(--t-border);
          margin-top: 1.4rem; }}
    h4, h5 {{ color: var(--t-muted) !important; font-weight: 500 !important; }}
    p, li, label, .stMarkdown {{ line-height: 1.6; }}
    [data-testid="stCaptionContainer"], .stCaption {{ color: var(--t-muted) !important; }}
    a {{ color: var(--t-accent) !important; }}
    hr {{ border-color: var(--t-border) !important; margin: 1.5rem 0 !important; }}

    /* --- Sidebar --- */
    [data-testid="stSidebar"] {{
        background-color: var(--t-card); border-right: 1px solid var(--t-border);
    }}
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: 1rem; }}
    [data-testid="stSidebarNav"] a {{ border-radius: 6px; }}
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background: var(--t-card2); border-left: 2px solid var(--t-accent);
    }}

    /* --- Métriques : une surface, pas de bordure, chiffre en évidence --- */
    div[data-testid="stMetric"] {{
        background-color: var(--t-card); border-radius: 8px; padding: 14px 16px;
        border: 1px solid var(--t-border); min-height: 104px;
    }}
    div[data-testid="stMetricLabel"] p {{ color: var(--t-muted) !important; font-size: .82rem; }}
    div[data-testid="stMetricValue"] {{ color: var(--t-text) !important; font-weight: 600;
        font-size: 1.65rem; font-family: 'IBM Plex Mono', ui-monospace, monospace; }}

    /* --- Boutons : accent réservé à l'action principale --- */
    .stButton > button, .stDownloadButton > button {{
        background-color: transparent; color: var(--t-text); border: 1px solid var(--t-border);
        border-radius: 6px; font-weight: 500; transition: border-color .15s, background-color .15s;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        border-color: var(--t-accent); color: var(--t-accent); background-color: transparent;
    }}
    .stButton > button:focus-visible {{ outline: 2px solid var(--t-accent); outline-offset: 2px; }}
    .stButton > button[kind="primary"] {{
        background-color: var(--t-accent); color: var(--t-bg); border-color: var(--t-accent); font-weight: 600;
    }}
    .stButton > button[kind="primary"]:hover {{ filter: brightness(1.1); color: var(--t-bg); }}

    /* --- Onglets : soulignement de l'onglet actif --- */
    .stTabs [data-baseweb="tab-list"] {{ gap: 1.2rem; border-bottom: 1px solid var(--t-border); }}
    .stTabs [data-baseweb="tab"] {{ padding: .5rem .1rem; color: var(--t-muted); font-weight: 500; }}
    .stTabs [aria-selected="true"] {{ color: var(--t-text); }}
    .stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--t-accent); height: 2px; }}
    .stTabs [data-baseweb="tab-border"] {{ display: none; }}

    /* --- Expanders, popovers, champs --- */
    [data-testid="stExpander"] {{
        border: 1px solid var(--t-border); border-radius: 8px; background-color: var(--t-card);
    }}
    [data-testid="stExpander"] summary {{ font-weight: 500; }}
    [data-testid="stPopoverBody"] {{ background-color: var(--t-card); border: 1px solid var(--t-border); }}
    [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
        background-color: var(--t-card2) !important; border-color: var(--t-border) !important;
    }}

    /* --- Tableaux --- */
    div[data-testid="stDataFrame"] {{
        border: 1px solid var(--t-border); border-radius: 8px; overflow: hidden;
    }}

    /* --- Messages --- */
    div[data-testid="stAlert"] {{ border-radius: 8px; border: 1px solid var(--t-border); }}
    div[data-testid="stAlert"] p, div[data-testid="stAlert"] li {{ color: var(--t-text) !important; }}
    /* Barre de progression : piste discrète, remplissage en accent, libellé lisible */
    [data-testid="stProgressBarTrack"] {{ background-color: var(--t-card2); border-radius: 4px; height: 6px; }}
    [data-testid="stProgressBarTrack"] > div {{ background-color: var(--t-accent); border-radius: 4px; }}
    .stProgress p {{ color: var(--t-muted); font-size: .85rem; }}

    /* --- Barres de défilement discrètes --- */
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-thumb {{ background: var(--t-border); border-radius: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}

    @media (max-width: 768px) {{
        .block-container {{ padding: 1.2rem 1rem 3rem; }}
        div[data-testid="stMetric"] {{ margin-bottom: 8px; }}
        div[data-testid="stMetricValue"] {{ font-size: 1.4rem; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
    </style>
    """


def apply_theme():
    """À appeler en haut de chaque page (après st.set_page_config)."""
    st.markdown(build_css(get_active_palette()), unsafe_allow_html=True)
