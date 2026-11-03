"""hwpanel_i18n: Sprachwahl und Übersetzungen für CLI und GUI.

Die Texte im Quellcode sind Englisch. Jede Sprache ist eine Datei locales/<code>.json, die den
englischen Text auf die Übersetzung abbildet; der Schlüssel "_name" ist der Anzeigename der Sprache.
Fehlt ein Eintrag, erscheint der englische Text. Es gibt keinen Kompilierschritt: Eine neue Sprache
entsteht, indem man eine JSON-Datei anlegt.

Platzhalter in Python-Texten sind {name}, in QML-Texten %1 (beide gelten in derselben Datei).
"""

import json
import os
import re
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent / "locales"
SOURCE_LANG = "en"
META_KEY = "_name"

_state = {"lang": SOURCE_LANG, "catalog": {}}


def _code(value):
    """'de_DE.UTF-8' -> 'de'; 'C', 'POSIX' und Leeres -> None."""
    m = re.match(r"([A-Za-z]{2,3})(?![A-Za-z])", value or "")
    return m.group(1).lower() if m else None


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def available(locale_dir=None):
    """Verfügbare Sprachen als {Kürzel: Anzeigename}, nach Kürzel sortiert. Englisch ist immer dabei."""
    names = {SOURCE_LANG: "English"}
    for f in Path(locale_dir or LOCALE_DIR).glob("*.json"):
        data = _read(f)
        if data is not None:
            names[f.stem.lower()] = str(data.get(META_KEY) or f.stem)
    return dict(sorted(names.items()))


def system_languages(env=None):
    """Sprachen des Systems in Reihenfolge der Vorliebe (wie gettext: LANGUAGE zählt nicht bei C/POSIX)."""
    env = os.environ if env is None else env
    locale = next((env[k] for k in ("LC_ALL", "LC_MESSAGES", "LANG") if env.get(k)), "")
    if _code(locale) is None:
        return []
    out = []
    for part in env.get("LANGUAGE", "").split(":") + [locale]:
        code = _code(part)
        if code and code not in out:
            out.append(code)
    return out


def resolve(preference=None, env=None, locale_dir=None):
    """Kürzel der zu nutzenden Sprache. 'auto' (oder leer) folgt dem System, sonst gilt die ausdrückliche Wahl.
    Ohne passenden Katalog gilt Englisch."""
    langs = available(locale_dir)
    pref = (preference or "auto").strip().lower()
    if pref == "auto":
        return next((c for c in system_languages(env) if c in langs), SOURCE_LANG)
    code = _code(pref)
    return code if code in langs else SOURCE_LANG


def load(lang, locale_dir=None):
    """Katalog einer Sprache ohne Meta-Eintrag; unbekannt oder defekt: leer (dann gilt der Quelltext)."""
    data = _read(Path(locale_dir or LOCALE_DIR) / f"{lang}.json") or {}
    return {k: v for k, v in data.items()
            if k != META_KEY and isinstance(v, str) and v.strip()}


def set_language(lang, locale_dir=None):
    """Stellt die Sprache für tr() ein und gibt das tatsächlich gewählte Kürzel zurück."""
    if lang not in available(locale_dir):
        lang = SOURCE_LANG
    _state.update(lang=lang, catalog=load(lang, locale_dir))
    return lang


def language():
    return _state["lang"]


def catalog():
    """Der Katalog der aktuellen Sprache (für den Qt-Übersetzer der GUI)."""
    return _state["catalog"]


def tr(text, **kw):
    """Übersetzt einen englischen Quelltext in die aktuelle Sprache und setzt {Platzhalter} ein."""
    out = _state["catalog"].get(text, text)
    if not kw:
        return out
    try:
        return out.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text.format(**kw)   # fehlerhafter Platzhalter in der Übersetzung: lieber Englisch als ein Absturz
