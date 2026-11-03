# Contributing

**Languages:** English · [Deutsch](CONTRIBUTING.de.md)

Thanks for your interest! Please note:

- This is a one-person project. Please be patient with answers and reviews.
- Only submit code that you understand and have tested yourself.
- In a pull request, describe what changes, why, and how you tested it.
- Bug reports: please include the version, system/distribution, kernel, hardware, logs and steps to reproduce. The bug report template asks for exactly this.

## Development

- Run the tests before and after your change: `python3 -m unittest discover -s tests`. They run on emulated hardware: no AMD GPU is needed and no hardware settings are changed. The GUI tests need PySide6 and are skipped without it (with PySide6 set `QT_QPA_PLATFORM=offscreen`).
- New behavior needs a test. Bug fixes should come with a test that fails without the fix.
- Hardware safety comes first. The daemon writes only to the whitelist of sysfs paths in `write_allowed()` and rejects values above the driver defaults. Changes to this, to the fan protection rules or to `hwpanel.service` need tests; `tests/test_service_unit.py` guards the hardening.
- Language: comments, docstrings, failure messages of the tests and the source texts of the interface are English. German (and any other language) lives in `locales/<code>.json`. `tests/test_i18n.py` checks this.
- New or changed text that users see: wrap it in `qsTr()` (QML), `tr()` (Python) or, for messages of the daemon, `Msg()`, and add the translation to `locales/de.json`. A new language is just a new JSON file; see "Translations" in the [README](README.md).
