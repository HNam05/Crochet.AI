# Arbeitsplan bis 26. Oktober 2026

Stand: 19. Oktober 2026. Das Datum ist das gewünschte Lieferziel, keine belegte
Fertigstellungsprognose. Der vollständige vereinbarte Umfang bleibt R1–R4 aus
[dem Umsetzungsplan](BACKEND_IMPLEMENTATION_ROADMAP.md). Eine experimentelle
Softwarelieferung wird nicht als vollständige Backend-Abnahme bezeichnet.

## Umsetzung beschleunigen

- R1 als durchgehenden Ablauf bearbeiten: Erzeugung, unabhängige Prüfung,
  Kandidatenauswahl, dauerhafter Job, Export und nachvollziehbarer Fehlerfall.
  Neue Kleidungs-/Spitzenbereiche beginnen erst nach diesem Integrationsziel;
  ihre bestehenden Zusagen und Abnahmekriterien bleiben erhalten.
- Zusammenhängende Arbeitspakete mit gezielten Tests liefern. Eine vollständige
  Regression und ein installiertes Paket am Integrationspunkt prüfen. Keine
  wiederholten Gesamtläufe nach jeder kleinen Änderung.
- Einen begrenzten Implementierungsworker einsetzen; die Hauptinstanz entscheidet
  Verträge und integriert. Bei riskanter Prüf-/Numerikarbeit einen unabhängigen
  Reviewer nutzen. Keine rekursive Delegation oder doppelte Implementierung.
- Gemessene Engpässe beseitigen. Die aktuelle Änderung vermeidet wiederholte
  erfolgreiche Schemaprüfungen innerhalb eines Prüflaufs. Eingaben, Fehler,
  Semantikprüfungen und sämtliche Pflichtgates bleiben geprüft.
  Vier Vergleichsläufe desselben gespeicherten Falls ergeben einen Median von
  43,34 auf 13,56 Sekunden (3,20-fach), bei identischen kanonischen Belegen.
  Das ist eine lokale Messung unter paralleler Testlast, keine allgemeine
  Laufzeitgarantie; CPU-Zeitvergleich: 3,19-fach.
- Reale Häkel-/Messarbeit kann parallel laufen. Bestehende englische PDFs und
  das Messpaket verwenden; Messwerte, Profilfreigaben und Holdouts nicht erfinden.

## Kritischer Pfad

Die Tagesfenster sind Prioritäten. Ein fehlgeschlagenes Abnahmekriterium bleibt
offen und verschiebt abhängige Arbeit; ein Kalendertag schließt kein Gate.

| Fenster | Zusammenhängendes Ergebnis | Prüfkriterium / Abhängigkeit |
| --- | --- | --- |
| 19.10. | Erreichte numerische Fehler unabhängig rekonstruieren; wiederholte Schemaarbeit reduzieren | Tatsächliche Producer-Traces, gefälschte Terminals, spätere Hypothese, identische Prüfbelege mit/ohne Wiederverwendung; Regression und installiertes Paket |
| 20.–21.10. | Numerische Kandidatenprüfung und Auswahl verbinden; am 19.10. bereits implementiert | Additiver lokaler V5-Vertrag, frische V0–V10-Prüfung, exakte Auswahl über den vollständig erfassten Satz; Integration und installierte Ausführung belegen, keine physikalische Freigabe ableiten |
| 21.–22.10. | Modell-/Vergleichsgrenzen an repräsentativen geschlossenen SC-Fällen prüfen | Erfolgsfälle und nicht konvergierte/zu teure Fälle; jedes harte Geometriekriterium einzeln; keine nachträgliche Lockerung von Schwellen oder synthetische Kalibrierfreigabe |
| 22.–23.10. | Gesamtablauf in API/CLI/dauerhaften Jobs abschließen | Gleiche Quell-/Installationsantworten, Wiederanlauf, Abbruch, Ressourcenlimit und unveränderte gespeicherte Projekte/PDFs |
| 23.–25.10. | Betriebs-/Sicherheitslücken und empirische Evidenz auswerten | Konkrete B7/B8/B11-Checkliste mit positivem Beleg oder offenem Gate; Backup/Restore und Eingabegrenzen; unabhängige reale Mess-/Holdout-Daten erforderlich |
| 26.10. | Lieferstand gegen R1-Kriterien prüfen und veröffentlichen | Vollständige Regression, Kompatibilität, installiertes Paket und nachvollziehbarer R1-Abnahmebericht; ohne erfüllte Pflichtgates bleibt die Abnahme offen |

## Unmittelbar nächstes Implementierungspaket

Der Kreis zwischen lokalem V5-Beweis und späterer numerischer Auswahl ist im
additiven [Auswahlvertrag](ANALYTIC_NUMERICAL_SELECTION_V1.md) aufgelöst.
V0–V10 bleiben Pflicht; nur die abschließende Batch-Entscheidung liegt außerhalb
der lokalen Kandidatenprüfung. Der Standardvertrag bleibt unverändert. Exakte
lexikografische Metrikordnung und IR-Hash behandeln unvergleichbare Vektoren und
Gleichstände ohne gewichteten Durchschnitt. API/CLI/Jobs und gespeicherte Projekte
haben den verbundenen Ablauf. Zwei vollständig bestandene synthetische Fälle
prüfen die Auswahlmechanik, keine reale Materialkalibrierung.

Nächstes zusammenhängendes Paket: Produktionskonvergenz an repräsentativen
geschlossenen SC-Fällen untersuchen und die konkret erreichten Modellgrenzen
schließen. Dazu die bereits vorhandenen Material-/F0-Verträge und Messpakete
verwenden, kleine und realistische Skalen getrennt auswerten, Abschluss-/Druck-
und Kontaktgesetze mit identifizierten Parametern prüfen und fehlende Evidenz
explizit lassen. Vor Änderungen an Generator oder unabhängiger Prüfung jeweils
die betroffene Seite begrenzen; keine gemeinsame Anpassung an ein gewünschtes
Ergebnis. Produktionsschwellen und Kalibrierfreigaben dürfen nicht aus den
permissiven Integrationsfixtures übernommen werden. Danach folgen
Idealflächen-/Unsicherheitsabdeckung, authentifizierte Quellen und die konkrete
Betriebsabnahme. Die übrigen Wochenfenster und R1–R4-Anforderungen bleiben offen,
bis ihre eigenen positiven Belege vorliegen.

## Grenzen der Wochenzusage

Für R1 fehlen weiterhin produktiv nachgewiesene Konvergenz, identifizierte
Material-/Abschlussgesetze, kalibrierte Form- und Robustheitsprofile,
authentifizierte Evidenz und vollständige Betriebsabnahme. R2/R3 enthalten
zusätzlich Geometrieplanung für Verzweigungen/Montage, offene/flache Physik,
allgemeine Flächen, Kleidung und Spitzen. Diese Softwarelücken sind nicht bloß
ausstehende Häkeltests. Eine vollständige R4-Abnahme bis zum Wochentermin ist
mit dem aktuellen Nachweisstand nicht seriös zugesichert.

Der nächste Chat beginnt mit [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md). Dort
stehen tatsächlich ausgeführte Prüfungen, Messungen, aktueller Commit und
Laufzeitbelege. Dieser Plan ersetzt keine davon.
