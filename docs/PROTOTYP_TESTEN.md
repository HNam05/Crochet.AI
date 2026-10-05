# Crochet.AI lokal testen

Der lokale Prototyp unterstützt Kugeln, Ellipsoide, geschlossene Zylinder und
Kegel, Kapseln sowie eine birnenartige organische Testform, einen Faden
und feste Maschen mit Zu- und Abnahmen in fortlaufenden Runden. Die Anleitung
ist ein Versuchsmuster. Ob Form und Größe wirklich passen, prüfst du beim Häkeln.

## Starten

Im Projektordner `Start-CrochetPrototype.cmd` öffnen. Alternativ:

```powershell
.\.venv\Scripts\python.exe tools/run_prototype.py
```

Den gestarteten Prozess laufen lassen und `http://127.0.0.1:8765` im Browser
öffnen. Das Schließen/Beenden des Prozesses stoppt den Server. Daten bleiben
im Projekt unter `artifacts/local-prototype` erhalten. Ein anderer Port ist
mit `python tools/run_prototype.py --port 8766` möglich.

Python 3.11 oder neuer und die Projektabhängigkeiten sind erforderlich. Auf
diesem Rechner werden die vorhandenen Abhängigkeiten verwendet. Es gibt keine
Anmeldung und keine Cloudübertragung. Für einen anderen Rechner gilt die
Installationsanleitung in `BACKEND_RUNTIME.md`.

## Einen Häkeltest durchführen

1. Erzeuge zuerst eine kleine Kugel, zum Beispiel 40 mm Durchmesser. Die
   vorbelegten Materialwerte sind Beispieldaten; ersetze sie durch deine Probe.
2. Miss feste Maschen und Runden über 10 cm unter möglichst gleichen Bedingungen
   wie beim späteren Objekt. Verwende eine runde Probe, die entspannt und noch
   nicht gefüllt ist. Nadelgröße und Garnbezeichnung dienen der Dokumentation.
   Zähle die Abstände zwischen Maschenmitten beziehungsweise Rundenmitten über
   die gemessenen 100 mm: 26 Mitten spannen 25 Abstände auf. Die Materialwerte
   verwenden diese Abstände, damit Randmaschen nicht doppelt gezählt werden.
3. Erzeuge die Anleitung. Kontrolliere die Rundenzahlen und lade Anleitung und
   vollständiges Projekt herunter. Die kontrollierte Pattern-V1-Datei enthält
   zusätzlich die genaue Konstruktion mit Einstechstellen.
   Mit „Anleitung als PDF“ erhältst du eine druckbare Datei mit Materialwerten,
   geordneten Runden, Zu-/Abnahme-Erklärung und einem Testbericht. Diese Datei
   funktioniert ohne Server, Konto oder Zugriff auf deinen Rechner.
4. Häkle in fortlaufenden Runden. Markiere den Rundenbeginn. Eine Zunahme bedeutet
   zwei feste Maschen in dieselbe Einstechstelle; eine Abnahme verwendet die zwei
   angegebenen Einstechstellen und erzeugt eine neue Masche. Beachte bei
   ausdrücklich genannten Positionen die genaue vorherige Runde.
5. Nutze Vor/Zurück und die Rundenauswahl, um die aktuelle Anweisung aufzurufen.
   Das Modell lässt sich drehen; ausgewählte Maschen und Anweisungen gehören
   zusammen. Die Vorschau zeigt den schematischen Maschenaufbau. Sie berechnet
   keine physikalisch bestätigte Endform und keine Füllwirkung.
   Mit „Häkelansicht öffnen“ stehen Objekt, aktuelle Anweisung und Maschenzähler
   gemeinsam im Vordergrund. „Bisheriger Aufbau“ zeigt die bereits bestätigten
   Schritte plus die markierte nächste Masche; „Gesamtes Muster“ zeigt die
   Übersicht. „Entwurf bearbeiten“ bringt dich zu den Eingaben zurück.
6. Bei einer gefüllten Probe vor dem abschließenden Verschließen füllen. Das
   Schließen des Restlochs und Vernähen sind handwerkliche Abschlussarbeiten;
   die geometrische Wirkung dieses Abschlusses ist noch nicht simuliert.
7. Miss Breite und Höhe des fertigen Objekts. Speichere unter Rückmeldung, ob es
   funktioniert hat, welche Runde Schwierigkeiten machte, und ob du etwas
   ändern musstest. Lade den Testbericht herunter oder schicke ihn hier mit
   deinen Notizen und gegebenenfalls Fotos.

Fortschritt ist eine Position in der Anleitung, kein Nachweis fertiger Maschen.
Zurückgehen und Wiederöffnen bleiben möglich. Jede Rückmeldung gehört zur
exakten Anleitung und ihren Materialwerten. Eine neue Form bekommt einen
eigenen Fortschritt; frühere Berichte bleiben erhalten.

## Eine andere Person häkeln lassen

Besorge zuerst Garn, Nadelgröße und Maschenprobe der Person, die tatsächlich
häkelt. Trage diese Werte hier ein, berechne das Muster und schicke die PDF.
Die lokale Browser-Adresse funktioniert nur auf deinem Rechner. Die Person
benötigt für die PDF weder das Programm noch dieselbe Wolle wie du.

Die Anleitung enthält eine Musterkennung und einen druckbaren Testbericht.
Lass dir den ausgefüllten Bericht oder ein Foto davon zurückschicken. Ordne die
Rückmeldung genau dieser Kennung zu; bei anderer Maschenprobe oder geänderten
Maßen ist eine neue Anleitung erforderlich. Es wird nichts automatisch versendet.

## Vergleichbare Testreihe

Verwende für alle drei Versuche dieselbe gemessene Maschenprobe, Garn und Nadel.
„Beispielmaße für diese Form laden“ ändert nur Formmaße; Materialwerte bleiben
erhalten. Berechne danach jeweils neu und exportiere eine eigene PDF.

| Versuch | Beispiel | Worauf achten? |
| --- | --- | --- |
| Grundform | Kugel, 40 x 40 mm | Rundenzählen, Breite/Höhe, Schließen des Restlochs |
| Gleichmäßiger Körper | Kapsel, 30 x 50 mm | Übergang von Rundung zu geradem Mittelteil, regelmäßige Runden |
| Organisch | Birne, 40 x 55 mm | Breiter Bauch und schmalerer oberer Bereich, Verteilung der Abnahmen |

Die Maße sind Entwurfsziele, keine zugesicherten Endmaße. Notiere Breite und
Höhe zunächst entspannt und ungefüllt und, falls gefüllt, anschließend separat.
Ändere während eines Vergleichs nicht still Garn, Nadel oder Spannung. Falls
eine Anleitung nicht ausführbar ist, stoppe an dieser Runde und notiere die
Änderung, die du zum Weiterhäkeln benötigen würdest. Diese kleine Reihe prüft
Bedienbarkeit und erste Formhypothesen; sie ersetzt keine Materialkalibrierung.

Zylinder und Kegel enthalten geschlossene Böden, keine offene Rohr-/Hutform.
Eine Kapsel benötigt mindestens so viel Höhe wie Durchmesser. Sehr große Formen
oder dichte Maschenproben können die begrenzte Suche überschreiten und werden
ausdrücklich abgelehnt. Birne ist eine feste, versionierte rotationssymmetrische
Testform; freie organische Modelle, Verzweigungen und Figuren bleiben offen.

## Was dein Bericht möglichst enthalten sollte

- Projekt oder Testbericht aus dem Prototypen.
- Garn, Nadel und tatsächlich verwendete Maschenprobe.
- Gewünschte und gemessene Breite/Höhe, mit oder ohne Füllung.
- Betroffene Runde/Anweisung und jede Änderung beim Häkeln.
- Ob Zählen, Einstechstellen und Abschluss verständlich waren.

Deine Angaben werden lokal gespeichert und als noch nicht geprüfter
Erfahrungsbericht geführt. Sie verändern weder die kanonische Konstruktion
noch automatisch ein Kalibrierungs- oder Verifikationsurteil. Die separate
Mobile-App ist der nächste vereinbarte Zugang nach diesem Browser-Prototypen.
