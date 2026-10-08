Update 0.5.0: Ist-Zustand aus ASIN-Listen

Ist-Zustand auslesen > ASIN-Liste hochladen (XLSX/CSV; ASIN, optional Name).
Marktplätze auswählen und Aufnahme starten. Ergebnisse erscheinen während des Laufs.
Gefundene Geschwister-ASINs werden mitgelesen. Sprache wird pro Markt festgelegt.
Varianten ansehen zeigt die gefundenen Merkmale und unklare Ergebnisse.
Stoppen lässt bereits fertige Ergebnisse stehen; Offene Prüfungen fortsetzen
arbeitet nur noch ausstehende Eingabe-ASINs/Marktplätze ab.
Jede neue Aufnahme erhält einen eigenen Verlauf. Soll-Familien bleiben unverändert.

Excel für diesen Markt exportiert eine XLSX-Datei. Alle Märkte als Excel-Paket
liefert eine ZIP-Datei mit einer XLSX je Markt, unabhängig vom Anzeigefilter.
Übersicht: jede Eingabe-ASIN einschließlich offener/fehlgeschlagener Prüfungen.
Varianten: gefundene ASINs mit Merkmalen, Links, Zeitpunkt und Lesestatus.
Identische Gruppen werden je Markt zusammengefasst; Eingabe-ASINs bleiben genannt.
Gelbe Felder Bewertung und Kommentar sind für die Prüfung durch Kolleg:innen.
Gelesen bedeutet auslesbar, nicht fachlich korrekt. Keine sichere Parent-ASIN-Ermittlung.
Läufe können während Amazon-Änderungen unterschiedliche Zustände erfassen; Zeitpunkte
bleiben pro Seite gespeichert. Blockierte/unvollständige Seiten sind gekennzeichnet.
Grenzen: 2.000 eindeutige Eingabe-ASINs; 500 geöffnete Varianten pro Gruppe.
Bei Überschreitung bleibt die Aufnahme ausdrücklich unvollständig.

Das Update nutzt die vorhandene EXE (Launcher-Protokoll 1).

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

