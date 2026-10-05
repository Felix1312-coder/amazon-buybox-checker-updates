Amazon Variation Monitor 0.4.0

EINMALIGE EINRICHTUNG
Alte App schließen. Amazon-Variation-Monitor-Setup-0.4.0.exe starten.
Die App installiert sich ohne Administratorrechte nach
%LOCALAPPDATA%\Programs\AmazonVariationMonitor.
Eine Verknüpfung wird auf dem tatsächlichen Windows-Desktop (auch OneDrive)
und im Startmenü angelegt. Danach immer dieses Symbol verwenden.
Bisherige Familien, Zeitplan und Verlauf bleiben unter
%LOCALAPPDATA%\AmazonVariationMonitor erhalten.

UPDATES
Die App prüft beim Start ihren eigenen Update-Kanal.
Unter Einstellungen: Nach Updates suchen / Update installieren.
Danach die App schließen und über dasselbe Symbol erneut öffnen.
Normale Funktionsupdates ersetzen nur das App-Bundle, nicht die EXE.
Ein Update-Fehler lässt die vorhandene App nutzbar.
Bei Änderungen an gebündelten Python-/Browser-Abhängigkeiten oder am
Startprogramm selbst kann ausnahmsweise ein neuer Installer nötig sein.

VERÖFFENTLICHUNG KÜNFTIGER UPDATES
Eigenständiger Kanal: Branch variation-monitor-updates im Repository
Felix1312-coder/amazon-buybox-checker-updates.
Version in package_update.py erhöhen und python package_update.py ausführen.
Zuerst variation-monitor-VERSION.zip auf diesen Branch hochladen,
danach latest.json ersetzen. Keine privaten Daten ins öffentliche Repository.
Die Manifest-Adresse ist fest in der App hinterlegt.
Der bestehende Workspace-Updatekanal wird nicht verändert.

DESKTOP-SYMBOL FEHLT?
Einstellungen > Desktop-Symbol erstellen. Alternativ installierte EXE öffnen.

TÄGLICHE PRÜFUNG
Die App muss geöffnet bleiben und der Rechner online sein.
Manuelle Prüfungen jederzeit über Jetzt alle prüfen / Prüfen / ASIN-Test.
Microsoft Edge oder Google Chrome muss installiert sein.

FAMILIEN / EXCEL
Bearbeiten ändert die Soll-Familie für künftige Prüfungen. Verlauf bleibt erhalten.
Pro ASIN sind Farbe, Stil und Größe kombinierbar. Freie Werte wie auf Amazon eingeben.
Adaptive Excel-Vorlage: gewünschte Merkmale wählen und herunterladen.
Import ersetzt enthaltene Familien je Marktplatz vollständig.
Unvollständige/gesperrte Amazon-Seiten führen zu Unklar, nicht automatisch Split.
