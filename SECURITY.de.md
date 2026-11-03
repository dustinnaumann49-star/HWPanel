# Sicherheit

**Sprachen:** [English](SECURITY.md) · Deutsch

Bitte melde Sicherheitsprobleme vertraulich per E-Mail an dustinnaumann49@gmail.com, nicht über öffentliche Issues. Ist für das Repository die private Meldung von Sicherheitslücken bei GitHub aktiviert, kannst du stattdessen diese nutzen (Reiter "Security", "Report a vulnerability"). Ich melde mich so bald wie möglich zurück.

## Was relevant ist

Der Daemon `hwpaneld` läuft als root und bietet den Mitgliedern einer Gruppe einen Unix-Socket (`/run/hwpanel/hwpanel.sock`) an. Relevant sind zum Beispiel: Wege, außerhalb der Whitelist von sysfs-Pfaden zu schreiben, Wege an den Grenzen vorbei (Werte über den Treiber-Standardwerten, die Schutzregeln des Lüfters), Zugriff auf den Socket für Benutzer außerhalb der Gruppe sowie Rechteausweitung über den Daemon, das Installationsskript oder die systemd-Unit.

## Was dazugehört

Die Version (`hwpanelctl --json info`, Feld `version`), dein System und Kernel, eine Beschreibung des Problems und, wenn möglich, Schritte zum Reproduzieren.

## Unterstützte Versionen

Korrekturen gehen in die jeweils neueste Version.
