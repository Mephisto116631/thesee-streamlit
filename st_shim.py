# _st_shim.py
# ==============================================================================
# SHIM STREAMLIT POUR EXÉCUTION HORS SERVEUR (CRON GitHub Actions)
# ==============================================================================
# data_pipeline.py / db.py / fred.py utilisent `st.cache_data`, `st.cache_resource`,
# `st.progress`, `st.warning`, `st.toast`, `st.secrets`, `st.empty`. Ces appels
# nécessitent normalement un serveur Streamlit actif (ScriptRunContext), absent
# dans un job CRON pur. Ce module fournit des remplacements minimalistes :
#   - les décorateurs @cache deviennent des no-op (pas de cache, on veut les
#     données fraîches à chaque run de toute façon)
#   - les affichages (progress/warning/toast) deviennent de simples print()
#   - st.secrets lit uniquement les variables d'environnement (os.environ),
#     ce qui correspond exactement à la façon dont GitHub Actions Secrets
#     sont exposés au job (env:).
#
# Utilisation : dans cron_sync.py, avant `import data_pipeline`, on injecte
# ce module dans sys.modules sous le nom "streamlit" pour que les imports
# `import streamlit as st` dans data_pipeline.py/db.py/fred.py récupèrent
# ce shim au lieu du vrai package.
# ==============================================================================
import os
from functools import wraps


class _FakeSecrets(dict):
    """Se comporte comme st.secrets mais lit os.environ (mappé par GitHub Actions)."""
    def __contains__(self, key):
        return key in os.environ

    def __getitem__(self, key):
        return os.environ[key]

    def get(self, key, default=None):
        return os.environ.get(key, default)


secrets = _FakeSecrets()


def cache_data(*args, **kwargs):
    """No-op : en CRON on veut toujours des données fraîches, pas de cache."""
    def decorator(func):
        @wraps(func)
        def wrapper(*a, **kw):
            return func(*a, **kw)
        return wrapper
    if len(args) == 1 and callable(args[0]):
        return decorator(args[0])
    return decorator


cache_resource = cache_data  # même comportement no-op


class _FakeProgressBar:
    def __init__(self, initial, text=""):
        if text:
            print(f"[CRON] {text}")

    def progress(self, value, text=""):
        if text:
            print(f"[CRON] {text}")

    def empty(self):
        pass


def progress(initial=0, text=""):
    return _FakeProgressBar(initial, text)


class _FakeEmpty:
    def info(self, msg):
        print(f"[CRON] {msg}")

    def warning(self, msg):
        print(f"[CRON][WARN] {msg}")

    def empty(self):
        pass


def empty():
    return _FakeEmpty()


def warning(msg):
    print(f"[CRON][WARN] {msg}")


def toast(msg, icon=""):
    print(f"[CRON] {icon} {msg}")


def info(msg):
    print(f"[CRON] {msg}")
