---
name: Bug report / Fehlerbericht
about: Something does not work as expected / Etwas funktioniert nicht wie erwartet
labels: bug
---

<!-- English or German is fine. / Englisch oder Deutsch ist beides in Ordnung. -->
<!-- Security problems: please do not post them here, see SECURITY.md. / Sicherheitsprobleme bitte nicht hier melden, siehe SECURITY.md. -->

**Description of the problem / Beschreibung des Problems**

**Steps to reproduce / Schritte zum Reproduzieren**
1.
2.

**Expected behavior / Erwartetes Verhalten**

**System information / Systeminformationen**
- hwpanel version (`hwpanelctl --json info`, field `version`):
- Distribution / kernel (`uname -r`):
- Graphics card (`lspci -nn | grep -i -E 'vga|display'`):
- CPU driver (`hwpanelctl info`, line "CPU"):
- GUI or command line? PySide6 version if GUI:

**Logs**

Output of `journalctl -u hwpanel -b` and, if possible, of `sudo python3 /usr/local/lib/hwpanel/hwpaneld.py --probe`
(read-only; contains the hardware model, the limits and your profile names, but no host name or serial numbers).
Bitte prüfe die Ausgabe vor dem Einfügen. / Please look through the output before pasting it.

```
```
