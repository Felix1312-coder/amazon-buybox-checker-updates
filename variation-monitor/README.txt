AMAZON VARIATION MONITOR 0.3.0 – Windows-Testversion

START
Amazon-Variation-Monitor.exe doppelklicken. Keine Python-Installation erforderlich.
Microsoft Edge oder Google Chrome muss installiert sein.
Die Oberfläche öffnet sich in einem eigenen Fenster (WebView2).
Falls WebView2 fehlt, öffnet sich die Oberfläche im Browser plus kleinem Startfenster.
App geöffnet lassen, wenn tägliche Prüfungen laufen sollen.

MANUELL TESTEN
Links „Manuell testen“ > ASIN und Marktplatz eingeben > „ASIN jetzt prüfen“.
Zeigt gefundene ASINs, Dimensionen und auslesbare Werte, ohne eine Soll-Familie vorauszusetzen.
Eine einzelne ASIN ohne Soll-Vorgabe wird NICHT automatisch als korrekt bewertet.
Ergebnis kann zur Kontrolle in die manuelle Familieneingabe übernommen werden.

FAMILIE ANLEGEN / BEARBEITEN
Unter Variantenfamilien: „Familie anlegen“ oder „Bearbeiten“ an einer gespeicherten Familie.
Familienname und Marktplatz sind änderbar. ASINs können hinzugefügt/entfernt werden.
Jede ASIN hat getrennte Felder. Über „Merkmal hinzufügen“ Typ auswählen und Soll-Wert eingeben.
Typen: Stil/Style, Farbe/Color, Größe/Size. Mehrere Merkmale pro ASIN sind möglich.
Ohne Merkmale werden nur ASIN-Verknüpfungen geprüft. Unvollständige Merkmale werden angezeigt.
„Änderungen speichern“ oder „Speichern & jetzt prüfen“. Die Familien-ID und Historie bleiben erhalten.
Änderungen werden nicht automatisch als neue Amazon-Beobachtung gewertet.

ADAPTIVE EXCEL-VORLAGE
In der App Farbe, Stil und/oder Größe auswählen. Nur gewählte Spalten werden heruntergeladen.
Ohne Auswahl: Familie, Marktplatz, ASIN. Gleicher Familienname + Markt bildet eine Soll-Familie.
Mehrere Märkte in einer Zelle, z.B. DE,FR,IT. Leere Soll-Werte werden nicht geprüft.
Merkmalstypen werden in den Sprachen der unterstützten Märkte erkannt (inkl. Arabisch).
Freie Soll-Werte sind keine automatische Übersetzung: bitte den tatsächlichen Amazon-Text eingeben.
50cm und 50 cm werden als gleich behandelt. Groß-/Kleinschreibung ist unerheblich.
Import ersetzt enthaltene Familien je Markt vollständig; andere bleiben unverändert.

WAS WIRD GEPRÜFT?
Jede Soll-ASIN wird separat geöffnet. Farb-, Stil-, Größenvarianten und Kombinationen
werden aus Variantenbereichen und expliziten Varianten-Daten auf der Seite gelesen.
Die ASIN-Verknüpfungen werden mit der Soll-Liste verglichen. Optionale Soll-Merkmale
werden je ASIN verglichen. Leere Soll-Merkmale werden nicht bewertet.
Allein die Reihenfolge, Preise und Bilder werden nicht verglichen.
Bei mehreren Dimensionen können Amazon-Seiten nur Teilmengen anzeigen; Ergebnisse
sind deshalb als sichtbare Abweichung zu verstehen, nicht als Beweis eines Katalog-Splits.
Nicht auslesbare Daten, Blockaden und Weiterleitungen werden als unklar ausgewiesen.
Abweichungen/unklare Seiten werden einmal erneut geprüft.

ZEITPLAN
Automatik zunächst aus; frei wählbare lokale Rechnerzeit.
App muss laufen, Rechner wach, Internet verfügbar.
Ausstehender Tageslauf wird beim Start nach der Soll-Zeit nachgeholt.
Ein automatischer Versuch pro Tag; manuelle Prüfungen bleiben unabhängig möglich.

DATEN / WORKSPACE
Separat unter %LOCALAPPDATA%\AmazonVariationMonitor\monitor.sqlite.
Kein Eingriff in den Workspace. Zum Sichern App schließen und diesen Ordner kopieren.
Historie bleibt gespeichert. UI zeigt letzte 500 Prüfungen; JSON-Export enthält alle.

TESTGRENZEN
Vergleich, Eingaben und Kombinationen werden automatisiert mit Testdaten geprüft.
Windows-Build prüft die verpackte EXE inklusive Browser-Treiber und Bedienoberfläche.
Ein Live-Test mit euren tatsächlichen Amazon-ASINs steht noch aus.
