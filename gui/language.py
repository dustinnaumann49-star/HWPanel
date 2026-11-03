"""Language of the GUI: setting (automatic or code), Qt translator for qsTr() and switching at runtime."""

import json
import os
from pathlib import Path

from PySide6.QtCore import Property, QCoreApplication, QObject, QTranslator, Signal, Slot
from PySide6.QtQml import qmlEngine

import hwpanel_i18n as i18n

CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hwpanel" / "gui.json"


class CatalogTranslator(QTranslator):
    """Qt translator: looks up the source text of qsTr() in the catalog of the current language."""

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        return i18n.catalog().get(sourceText)   # None means: no entry, the source text stays

    def isEmpty(self):
        return False


class Language(QObject):
    languageChanged = Signal()

    def __init__(self, config_path=None, env=None, locale_dir=None, parent=None):
        super().__init__(parent)
        self._path = Path(config_path) if config_path else None
        self._env, self._dir = env, locale_dir
        self._languages = [{"code": c, "name": n} for c, n in i18n.available(locale_dir).items()]
        self._setting = self._saved_setting()
        self._code = i18n.set_language(i18n.resolve(self._setting, env, locale_dir), locale_dir)
        self._translator = CatalogTranslator(self)
        QCoreApplication.installTranslator(self._translator)

    def _saved_setting(self):
        if not self._path:
            return "auto"
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "auto"
        value = data.get("language") if isinstance(data, dict) else None
        return value if value == "auto" or value in i18n.available(self._dir) else "auto"

    def _save(self):
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({"language": self._setting}) + "\n", encoding="utf-8")
        except OSError:
            pass   # the choice still applies until the program exits

    def close(self):
        if self._translator is not None:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None

    # ---- Properties for QML

    @Property(str, notify=languageChanged)
    def setting(self):
        """The choice: 'auto' or a language code."""
        return self._setting

    @Property(str, notify=languageChanged)
    def code(self):
        """The language actually in use."""
        return self._code

    @Property("QVariantList", constant=True)
    def languages(self):
        return self._languages

    # ---- Actions from QML

    @Slot(str)
    def setLanguage(self, setting):
        setting = (setting or "").strip().lower()
        if setting != "auto" and setting not in i18n.available(self._dir):
            return
        if setting == self._setting:
            return
        self._setting = setting
        self._code = i18n.set_language(i18n.resolve(setting, self._env, self._dir), self._dir)
        self._save()
        self.languageChanged.emit()

    @Slot(QObject)
    def retranslate(self, item):
        """Re-evaluates all qsTr() texts of the engine that the QML object belongs to."""
        engine = qmlEngine(item)
        if engine is not None:
            engine.retranslate()
