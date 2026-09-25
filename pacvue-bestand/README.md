# Pacvue Bestand – Updatekanal

Eigenständige Windows-App für Pacvue-Bestandsprüfungen.

## Einmaliger Einstieg

Version 1.0.0 enthält keinen Updater. Einmal `Pacvue-Bestand-Setup-1.0.1.exe` über die bisherige Installation installieren; vorher die App schließen. Der vorhandene Produktstamm, Ergebnisse und Pacvue-Login bleiben im bisherigen Datenordner erhalten.

## Update manuell veröffentlichen

In diesem Repository den Branch `felix-desktop-updates` und den Ordner `pacvue-bestand/` öffnen.

1. Aus dem fertigen Update-Paket zuerst `VERSION.bundle.gz` hier hochladen und committen.
2. Danach die dazugehörige `latest.json` hier hochladen bzw. ersetzen und committen.
3. In Pacvue Bestand unten **Nach Updates suchen** wählen oder die App neu starten.
4. Nach einer laufenden Bestandsprüfung **Neu starten & aktualisieren** wählen.

Dateinamen beibehalten. Nur das Bundle und die dazugehörige `latest.json` veröffentlichen. Die Setup-EXE dient der Erstinstallation. Das PRIVATE-Source-ZIP mit dem Signaturschlüssel bleibt privat.

Die App prüft Update-Signaturen und Datei-Prüfsummen. Die Bundles sind verschlüsselt und separat für diese App signiert. Ein Update wird erst nach erfolgreichem Start aktiv; bei einem fehlgeschlagenen Start wird beim nächsten Start die vorherige Version verwendet. Änderungen an Electron oder installierten Abhängigkeiten benötigen einen neuen Installer.

Der Kanal ist unabhängig vom EWS-Kanal im Ordner `workspace/`. Diese Einrichtung veröffentlicht noch kein aktives Update. Felix lädt die fertigen Dateien selbst hoch.
