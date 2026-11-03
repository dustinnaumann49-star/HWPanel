# Mitarbeit

**Sprachen:** [English](CONTRIBUTING.md) · Deutsch

Danke für dein Interesse! Bitte beachte:

- Das hier ist ein Ein-Personen-Projekt. Hab Geduld mit Antworten und Reviews.
- Reiche nur Code ein, den du verstehst und selbst getestet hast.
- Beschreibe bei Pull Requests: Was ändert sich, warum, und wie wurde getestet.
- Fehlerberichte bitte mit Version, System/Distribution, Kernel, Hardware, Logs und Schritten zum Reproduzieren. Die Vorlage für Fehlerberichte fragt genau das ab.

## Entwicklung

- Führe die Tests vor und nach deiner Änderung aus: `python3 -m unittest discover -s tests`. Sie laufen auf nachgebauter Hardware: Es wird keine AMD-GPU gebraucht, und es werden keine Hardware-Einstellungen verändert. Die GUI-Tests brauchen PySide6 und werden ohne übersprungen (mit PySide6 `QT_QPA_PLATFORM=offscreen` setzen).
- Pull Requests werden automatisch geprüft: GitHub lässt die Tests auf mehreren Python-Versionen ohne GUI laufen (die niedrigste ist die, die die README verspricht) und die GUI-Tests mit PySide6. Ein Pull Request sollte grün sein, bevor er übernommen wird. Der Workflow liegt in `.github/workflows/tests.yml`.
- Neues Verhalten braucht einen Test. Eine Fehlerbehebung sollte einen Test mitbringen, der ohne die Behebung fehlschlägt.
- Hardware-Sicherheit geht vor. Der Daemon schreibt nur auf die Whitelist von sysfs-Pfaden in `write_allowed()` und lehnt Werte über den Treiber-Standardwerten ab. Änderungen daran, an den Schutzregeln des Lüfters oder an `hwpanel.service` brauchen Tests; `tests/test_service_unit.py` bewacht die Härtung.
- Sprache: Kommentare, Docstrings, Fehlermeldungen der Tests und die Quelltexte der Oberfläche sind Englisch. Deutsch (und jede andere Sprache) steht in `locales/<kürzel>.json`. `tests/test_i18n.py` prüft das.
- Neue oder geänderte Texte, die Nutzer sehen: in `qsTr()` (QML), `tr()` (Python) oder, für Meldungen des Daemons, `Msg()` fassen und die Übersetzung in `locales/de.json` eintragen. Eine neue Sprache ist nur eine neue JSON-Datei, siehe "Übersetzungen" in der [README](README.de.md).
