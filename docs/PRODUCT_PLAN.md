# Produktplan: vom Rechenkern zum Werkzeug für Häkel- und Strickfans

Stand: 2026-11-02. Ziel: Wer gerne häkelt oder strickt, beschreibt eine Idee
(„kleiner grauer Hase“, „Mütze für 54 cm Kopfumfang“, „Schal 180 cm“) und
bekommt eine verständliche, rechnerisch geprüfte Anleitung, die nach dem
ersten Testteil zur eigenen Maschenprobe passt.

Grundsätze bleiben: Die KI schlägt nur Baupläne vor (ADR-0006), Maschenzahlen
rechnet der deterministische Solver, jede Anleitung ist bis zum echten Test
`NOT_VERIFIED / UNTESTED`.

## Phasen

| # | Phase | Ergebnis für Nutzer | Stand |
|---|---|---|---|
| 1 | Figuren aus Teilen | Teddy, Hase, Küken, Mütze; Annähpositionen, Augen, PDF | erledigt (ADR 0026) |
| 2 | Beschreibung → Bauplan | Freitext auf Deutsch; offline ohne KI, optional Claude | erledigt (dieser Stand) |
| 3 | Stricken | dieselben Teile/Mützen gestrickt (re, zun/kfb, 2 re zus) | erledigt, ohne CrochetIR |
| 4 | Flache Projekte | Schal, Decke (Reihen), Untersetzer (Runden) mit Streifen | erledigt, Reihen ohne CrochetIR |
| 5 | Kalibrierung | Testteil messen → Maschenprobe korrigieren → alles neu | erledigt (Einzelmessung) |
| 6 | Physischer Abgleich | Testserie Kugel/Arm/Ohr/Mütze, Modellgewichte anpassen | offen – braucht echte Häkelstücke |
| 7 | Konstruktions-Ausbau | ovaler Anfang (Lm-Kette), Farbflächen, Teile direkt anhäkeln, Ripp-/Bündchenmuster, halbe Stäbchen/Stäbchen | offen |
| 8 | Kleidung mit Verzweigung | Handschuhe (Daumen), Socken (Ferse), Pullover (Raglan) nach Körpermaßen | offen, eigener Solver |
| 9 | Hochladen als Vorlage | 3D-Modell (STL/OBJ) → Bauplan, ohne KI, im Browser (ADR 0029); Foto/Umriss | 3D-Modell erledigt (einteilig), Foto offen |
| 10 | Für alle nutzbar | kostenlose Web-Version auf GitHub Pages, Python im Browser (ADR 0028); später Teilen, Muster-Bibliothek | Web-Version erledigt |

## Was in diesem Stand umgesetzt ist

- **Texteingabe** (`figure_compose.py`): erkennt Motive (Teddy, Hase, Katze,
  Fuchs, Maus, Schwein, Frosch, Küken/Vogel, Schneemann, Pilz, Kugel, Mütze,
  Strickmütze, Schal, Decke, Untersetzer), Farben, Größen („15 cm“, „klein“),
  Kopfumfang, Flächenmaße („80 x 90 cm“), Stricken und Garnstärke. Optional
  Claude (`pip install anthropic`, API-Zugang) für freie Beschreibungen; jeder
  Vorschlag muss `parse_figure` bestehen, ungültige Antworten werden einmal
  korrigiert und sonst abgelehnt.
- **Stricken** als Technik der ganzen Figur: gleiche Rundenmathematik,
  Strick-Notation (DE/EN), Abschluss mit Abketten/Maschenstich.
- **Flache Formen**: `disc` (Kreis in Runden) und `rectangle` (Reihen mit
  Wende-Lm bzw. kraus rechts), Streifen, große Maße bis 2,5 m.
- **Kalibrierung**: gemessene Breite (rund, flach oder Umfang) und Höhe eines
  Teils → neue Maschenprobe `alt × geplant / gemessen`, auf 0,5 gerundet.
- Neue Vorlagen: Strickmütze, Schal, Babydecke, Untersetzer.

## Nächste Schritte (empfohlen)

1. **Testserie häkeln** (Phase 6): Arm + Ohr des Teddys, eine 6-cm-Kugel, eine
   Mütze. Abweichungen über die Kalibrierung erfassen und die Annahmen
   (Oberkanten-Modell, Lesbarkeitsgewichte) gezielt nachstellen.
2. **Ovaler Anfang und Bündchen** (Phase 7): häufigste Lücken bei Füßen,
   Schnauzen und Mützen.
3. **Reihen- und Strick-IR**: CrochetIR um Reihenarbeit erweitern (der
   vorhandene `flat_solver` ist die Basis); für Stricken eine eigene,
   versionierte Semantik statt Häkel-IR.
4. **Handschuhe/Socken** als erster verzweigter Kleidungs-Solver.
5. **Hochladen ausbauen** (Phase 9): 3D-Modelle mit Armen/Beinen automatisch
   in Teile zerlegen bzw. hochgeladene Teile annähen; Foto oder Umriss eines
   rundlichen Objekts als Profil – vollständig im Browser, ohne KI-Dienst.

Die Web-Version ist kostenlos und braucht keinen Server: GitHub Pages liefert
nur Dateien aus, gerechnet wird mit Pyodide im Browser der Besucher
(`tools/build_web.py`, Workflow `.github/workflows/pages.yml`).

Physische Genauigkeit lässt sich nicht durch Software allein erreichen; jede
Phase ab 6 braucht echte gehäkelte bzw. gestrickte Testteile.
