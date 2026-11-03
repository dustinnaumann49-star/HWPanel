# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle

"""hwpanel_i18n: language choice and translations for CLI and GUI.

The texts in the source code are English. Each language is a file locales/<code>.json that maps the
English text to its translation; the key "_name" is the display name of the language.
If an entry is missing, the English text appears. There is no compile step: a new language
is created by adding a JSON file.

Placeholders in Python texts are {name}, in QML texts %1 (both apply in the same file).
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
    """'de_DE.UTF-8' -> 'de'; 'C', 'POSIX' and empty -> None."""
    m = re.match(r"([A-Za-z]{2,3})(?![A-Za-z])", value or "")
    return m.group(1).lower() if m else None


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def available(locale_dir=None):
    """Available languages as {code: display name}, sorted by code. English is always included."""
    names = {SOURCE_LANG: "English"}
    for f in Path(locale_dir or LOCALE_DIR).glob("*.json"):
        data = _read(f)
        if data is not None:
            names[f.stem.lower()] = str(data.get(META_KEY) or f.stem)
    return dict(sorted(names.items()))


def system_languages(env=None):
    """Languages of the system in order of preference (as in gettext: LANGUAGE does not count with C/POSIX)."""
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
    """Code of the language to use. 'auto' (or empty) follows the system, otherwise the explicit choice applies.
    Without a matching catalog, English applies."""
    langs = available(locale_dir)
    pref = (preference or "auto").strip().lower()
    if pref == "auto":
        return next((c for c in system_languages(env) if c in langs), SOURCE_LANG)
    code = _code(pref)
    return code if code in langs else SOURCE_LANG


def load(lang, locale_dir=None):
    """Catalog of a language without the meta entry; unknown or broken: empty (then the source text applies)."""
    data = _read(Path(locale_dir or LOCALE_DIR) / f"{lang}.json") or {}
    return {k: v for k, v in data.items()
            if k != META_KEY and isinstance(v, str) and v.strip()}


def set_language(lang, locale_dir=None):
    """Sets the language for tr() and returns the code that was actually chosen."""
    if lang not in available(locale_dir):
        lang = SOURCE_LANG
    _state.update(lang=lang, catalog=load(lang, locale_dir))
    return lang


def language():
    return _state["lang"]


def catalog():
    """The catalog of the current language (for the Qt translator of the GUI)."""
    return _state["catalog"]


def tr(text, **kw):
    """Translates an English source text into the current language and fills in the {placeholders}."""
    out = _state["catalog"].get(text, text)
    if not kw:
        return out
    try:
        return out.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text.format(**kw)   # broken placeholder in the translation: better English than a crash


# ---------------------------------------------------------------- Messages of the daemon

class Msg:
    """Message of the daemon: English template plus arguments.

    str() gives the English text (journal, scripts, clients without translation). to_json() goes to the clients,
    which render the template in their language via message(). Arguments may be texts, numbers, further Msg
    and lists (lists are joined with ", "). User text always belongs in arguments, never in the template."""

    __slots__ = ("tpl", "args")

    def __init__(self, tpl, **args):
        self.tpl, self.args = tpl, args

    def __str__(self):
        return _render(self.tpl, self.args, translate=False)

    def __repr__(self):
        return f"Msg({self.tpl!r}, {self.args!r})"

    def to_json(self):
        return {"tpl": self.tpl, "args": {k: _jsonable(v) for k, v in self.args.items()}}


class MsgError(ValueError):
    """Error with a translatable message; str() is the English text, .msg the Msg for the protocol."""

    def __init__(self, tpl, **args):
        self.msg = Msg(tpl, **args)
        super().__init__(str(self.msg))


def _jsonable(v):
    if isinstance(v, Msg):
        return v.to_json()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v if v is None or isinstance(v, (str, int, float, bool, dict)) else str(v)


def _plain(v, translate):
    """An argument as a value for format(): messages and lists become text, numbers stay numbers."""
    if isinstance(v, Msg):
        return _render(v.tpl, v.args, translate)
    if isinstance(v, dict) and isinstance(v.get("tpl"), str):
        return _render(v["tpl"], v.get("args") or {}, translate)
    if isinstance(v, (list, tuple)):
        return ", ".join(str(_plain(x, translate)) for x in v)
    return v


def _render(tpl, args, translate):
    kw = {k: _plain(v, translate) for k, v in args.items()}
    text = _state["catalog"].get(tpl, tpl) if translate else tpl
    for candidate in (text, tpl):   # broken translation: better English than a crash
        try:
            return candidate.format(**kw)
        except (KeyError, IndexError, ValueError):
            continue
    return tpl


def message(m):
    """Renders a message from the protocol in the current language (m: {"tpl", "args"}, Msg or plain text)."""
    if m is None:
        return ""
    if isinstance(m, str):
        return m
    if isinstance(m, Msg):
        return _render(m.tpl, m.args, translate=True)
    if isinstance(m, dict) and isinstance(m.get("tpl"), str):
        return _render(m["tpl"], m.get("args") or {}, translate=True)
    return str(m)


def message_field(obj, key):
    """Text of a response field: prefers <key>_msg in the current language, otherwise the plain text (older daemon)."""
    m = obj.get(key + "_msg")
    return message(m) if m else str(obj.get(key) or "")


def message_list(obj, key):
    """Like message_field for lists (errors/errors_msg). If the lengths do not match, the plain texts apply."""
    plain = obj.get(key) or []
    msgs = obj.get(key + "_msg")
    if isinstance(msgs, list) and len(msgs) == len(plain):
        return [message(m) for m in msgs]
    return [str(x) for x in plain]
