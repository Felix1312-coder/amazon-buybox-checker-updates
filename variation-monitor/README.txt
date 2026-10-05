AMAZON VARIATION MONITOR 0.2.0 – Windows-Testversion

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

FAMILIE SPEICHERN / SOFORT PRÜFEN
Familienname, Markt und ASINs eingeben, eine Zeile je ASIN.
Optional: ASIN; Farbe; Stil; Größe. Nicht benötigte Werte leer lassen.
Beispielaufbau (durch echte Child-ASINs ersetzen):
ASIN; Taupe; Klassisch; M
ASIN; Creme; Klassisch; L
„Speichern & jetzt prüfen“ prüft sofort, unabhängig vom Zeitplan.
„Jetzt alle prüfen“ bzw. „Prüfen“ je Familie sind ebenfalls jederzeit verfügbar.

EXCEL
Vorlage in der App herunterladen. Pflicht: Familie, Marktplatz, ASIN.
Optional: Variante (Anzeigename), Farbe, Stil, Größe.
Gleicher Familienname + Marktplatz bildet eine gewünschte Familie.
Mehrere Märkte in einer Zelle, z.B. DE,FR,IT, sind möglich.
Merkmalswerte sind sprachabhängig; Soll-Werte in der Sprache des Marktes eintragen.
Import ersetzt enthaltene Familien pro Markt vollständig. Andere bleiben erhalten.

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
