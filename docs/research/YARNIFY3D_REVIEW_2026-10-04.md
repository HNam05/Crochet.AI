# Yarnify3D: Produktvergleich und Empfehlungen

Stand: **2026-10-04**, Europe/Berlin. Research-ID: `RQ-PRODUCT-YARNIFY-2026-10-04`.
Frage: Welche öffentlich belegten Ideen von Yarnify3D helfen Crochet.AI, ohne
Konstruktionssemantik, unabhängige Prüfung oder Backend-Abnahme zu schwächen?
Owner: Produkt/Architektur im Hauptchat. Status: Quellenvergleich abgeschlossen;
praktischer Editorvergleich und physische Bewertung offen.

## Ergebnis

**ESTABLISHED, als dokumentierter Produktumfang:** Yarnify3D konzentriert sich
auf selbst geschriebene Häkelanleitungen, deren 3D-Vorschau und die Begleitung
beim Häkeln. Öffentlich beschrieben ist damit überwiegend
**Anleitung → Vorschau → Herstellung**. Ein automatischer Solver für beliebige
Zielmeshes oder eine Bild-/Prompt-zu-Anleitung-Pipeline wurde in den untersuchten
öffentlichen Seiten nicht belegt. Das ist eine Grenze dieser Recherche, keine
Aussage über unveröffentlichte Funktionen. [Startseite](https://yarnify3d.com/),
[Einführung](https://yarnify3d.com/docs/getting-started/introduction).

**ENGINEERING DECISION:** Die bestehenden Projektgrenzen bleiben erhalten.
Crochet.AI verfolgt **DesignSpec/Zielgeometrie → deterministische Konstruktion →
unabhängige Prüfung → Anleitung**. Der Vergleich liefert Empfehlungen für die
spätere Produktphase; er autorisiert weder neue Features noch einen vorgezogenen
Frontend-Bau. Unsere Architektur bietet mögliche Differenzierung, aber noch
keinen Nachweis eines besseren fertigen Produkts. Nach diesem Vergleich hat
der Nutzer einen lokal testbaren Browser-Prototypen ausdrücklich beauftragt.
Diese spätere Freigabe und der begrenzte Umfang stehen in
[`LOCAL_PROTOTYPE_V1.md`](../LOCAL_PROTOTYPE_V1.md); die vorherige Aussage zur
Reihenfolge ist damit für diesen Häkeltest überholt.

## Zwei Live-Funktionen ausdrücklich unterscheiden

Der Nutzer hebt beide Funktionen als besonders relevant hervor:

1. **Live Object Generator beim Entwerfen:** Aus den eingegebenen
   Häkelanweisungen wird fortlaufend ein 3D-Objekt aufgebaut. Änderungen an
   unterstützten Anweisungen aktualisieren die Form. Die dokumentierte
   Generierungsrichtung ist Anleitung zu Objekt.
   [Editor](https://yarnify3d.com/docs/editor/editor-overview).
2. **Live Crochet Steps beim Herstellen:** Der aktuelle Schritt und der dazu
   passende digitale Bauzustand werden zusammen angezeigt. Die Bilder zeigen
   verschiedene Bauzustände bis zum fertigen Modell; die Dokumentation erklärt
   die Navigation pro Anweisung oder Masche. Das Fortschalten erfolgt durch
   Nutzereingabe; eine automatische Erkennung real gehäkelter Maschen wurde
   hier nicht belegt.
   [Live Crochet](https://yarnify3d.com/docs/live-crochet/live-crochet-overview).

**FUTURE, Empfehlung:** Crochet.AI sollte beide Modi als eigenständige
Produktfunktionen einplanen: eine fortlaufend aktualisierte Entwurfsansicht und
eine schrittweise Herstellungsansicht. Beide beziehen sich auf denselben
validierten CrochetIR-Stand, haben aber unterschiedliche Interaktionen und
Sessionzustände. Im Häkelmodus sollen aktuelle Masche, Ansatzstelle, Anleitung
und bisheriger Aufbau zusammenpassen. Die digitale Fortschrittsdarstellung
bleibt eine Darstellung der geplanten Konstruktion; ein physisch belastbarer
Zwischenzustand erfordert zusätzlich ein Modell mit geeigneten Randbedingungen.

## Methode und Grenzen

- Drei vom Nutzer übermittelte Bilder visuell untersucht. Aufnahmedatum,
  ursprünglicher Beitrag und verwendete App-Version sind unbekannt.
- Offizielle Startseite, Dokumentation, Stitch-/Syntax-Referenz, Editor-, Block-,
  Live-Crochet- und Musterverwaltung, Changelog sowie Nutzungs-/Datenschutzseiten
  am obigen Datum gelesen. Keine externen Implementierungsdateien konsultiert.
- Im Browser Startseite, Marketplace und Dashboard-Zugang geprüft. Dashboard
  leitete zu `login?returnTo=%2Fdashboard` um. Kein Konto angelegt, keine Daten
  hochgeladen und keine eigenen Anleitungen in der App ausgeführt.
- Der geladene Marketplace zeigte im untersuchten Besucherzustand null Treffer.
  Daraus folgt weder, dass es weltweit keine Muster gibt, noch dass keine Nutzer
  oder Verkäufe existieren. Keine Umsatz-/Nutzerzahlen ermittelt.
- Der Changelog listete als jüngsten sichtbaren Eintrag **v0.27.0 vom
  2026-09-27**. Das ist ein Veröffentlichungsstand des Changelogs, kein verifizierter
  Build-Identifier der ausgelieferten App. [Changelog](https://yarnify3d.com/changelog).
- `ESTABLISHED` bei Anbieterquellen bedeutet: Diese Aussage ist dort dokumentiert.
  Es bedeutet hier keinen unabhängigen Funktionstest oder physischen Nachweis.
  Empfehlungen sind `FUTURE`; unbelegte technische Schlussfolgerungen sind
  `HYPOTHESIS`.

Lokaler Vergleich: HEAD `18674c1a9d68b401b80f4a0ec1cdfcf602c0953a` **plus vorhandene
uncommittete Änderungen**. Die aktuellen Runtime-/Acceptance-Dokumente wurden
gelesen; der Commit allein reproduziert diesen Arbeitsstand nicht. Insbesondere
wurden alte Testzahlen nicht als aktuelle Evidenz übernommen.

## Was die drei Bilder zeigen

| Bild | Sichtbare Beobachtung | Bedeutung und Grenze |
| --- | --- | --- |
| 1 | Gelbe kugelförmige Maschenmarker am Anfang; Runden mit Zunahmen; hervorgehobene Anweisung; große Anzeige `6/6 SC`; Vor/Zurück und Farbanzeige | Frühzeitige Sichtbarkeit des Baufortschritts und klare aktuelle Aufgabe. Kugeln sind eine anschauliche Abstraktion; sie belegen keine Garnkontakt- oder Maßsimulation. |
| 2 | Eine offene schalenartige Zwischenform; Runden mit 60 Maschen; andersfarbige Textabschnitte; Anzeige `1/60 SC` | Auch Zwischenzustände sind nützlich. Ein Häkelmodus braucht den aktuellen Bauzustand und nachvollziehbare Farbwechsel, nicht nur ein fertiges Endbild. Die genaue Zählkonvention ist aus dem Bild allein nicht bestimmbar. |
| 3 | Froschähnliches mehrfarbiges Gesamtmodell; separate Augen-/Pupillenanweisungen; sichtbare Näh-/Montagehinweise; Teil abgeschlossen | Das Beispiel umfasst eine Montage mehrerer Elemente. Es ist kein Nachweis einer nahtlosen Gesamtkonstruktion. Ein Hinweis verlangt ausdrücklich eine Häkelprobe zur Kontrolle von Maschenprobe und Proportionen. |

Die Bilder zeigen eine mobile Darstellung mit einer überlagernden Vorschau.
**HYPOTHESIS:** Eine große Überlagerung kann Anweisung und Kontext verdecken;
das ist eine zu prüfende UX-Frage, kein gemessener Bedienfehler.

Bildidentität, SHA-256; Originale lagen beim Review im lokalen Temp-Ordner:

- `codex-clipboard-bc40d67a-fac9-4566-86f3-34a952c3719b.png`:
  `975b68c8c3b73b85785f32c3fa1311cc623dbb3712e38e33e62b51f36e00224c`
- `codex-clipboard-5434288a-6a8a-475c-aa37-e1dd184a846f.png`:
  `475212f4efa8f11c052a3c8177cfb2451700cb1a7db079d97cc6d43f2cfbbc5f`
- `codex-clipboard-228889e2-ed53-4628-9522-f9a4f6c6e998.png`:
  `eb23679c558a3695ee48071d9ea4150f38857a00c76006f34880532df2d3ae54`

Die Bildbeobachtungen bleiben hier erhalten. Die proprietären Bilder und darin
enthaltenen Muster werden gemäß [Research-Policy](../RESEARCH.md) nicht als
Projektassets, Spezifikationen oder Testfixtures übernommen. Temp-Dateien sind
keine dauerhafte Bildarchivierung.

## Öffentlich dokumentierte Idee und Grenzen

**ESTABLISHED, Editor:** Texteditor mit Vervollständigung, Fehlerhinweisen,
automatischen Zählern und 3D-Vorschau; anklickbare Maschenknoten verweisen auf
zugehörige Textstellen. PDF-Export kann Metadaten und Zwischenbilder enthalten.
Physik und Darstellungsqualität sind einstellbar. Die mobile Vorschau liegt als
verschiebbares Fenster über dem Text.
[Editor-Dokumentation](https://yarnify3d.com/docs/editor/editor-overview).

**ESTABLISHED, visuelles Schreiben:** Blockmodus strukturiert Teile, Reihen,
Anweisungen und Farben. Die Dokumentation warnt vor unvollständiger Übertragung
zwischen Text und Blöcken. Der neuere Changelog beschreibt überarbeitete
Wiederholungs-/Zielblöcke; die vollständige verlustfreie Abdeckung wurde hier
nicht getestet.
[Blockmodus](https://yarnify3d.com/docs/editor/editor-block),
[Release v0.27.0](https://yarnify3d.com/changelog/multilingual-parts-in-3d-and-block-mode).

**ESTABLISHED, Häkelbegleitung:** Live Crochet kann nach Anweisung oder einzelner
Masche navigieren. Teile sind einklappbar; aktuelle Anweisungen, Zähler,
Fortschritt, Notizen und gegebenenfalls Tutorials werden angezeigt. Die Vorschau
zeigt den bisherigen Stand. Fertige Teile bleiben sichtbar. Zeitangaben sind
Schätzungen. Tastatursteuerung wird dokumentiert.
[Live Crochet](https://yarnify3d.com/docs/live-crochet/live-crochet-overview),
[Tastatursteuerung](https://yarnify3d.com/docs/keyboard-shortcuts/live-crochet).

**ESTABLISHED, Syntax:** Eigene US-basierte Schreibweise mit Reihen/Runden,
Wiederholungen, Teilüberschriften, Kommentaren und Farben auf unterschiedlichen
Ebenen. Teile werden unabhängig dargestellt; Kommentare werden nicht als
ausführbare Anweisungen ausgewertet. Wenden wird implizit behandelt.
[Syntaxreferenz](https://yarnify3d.com/docs/crochet-syntax/syntax-reference).

**ESTABLISHED, Dokumentationsunsicherheit:** Der Quick Start bezeichnet
Gruppierungszeichen zunächst als austauschbar, erklärt später jedoch
unterschiedliche Anwendungen mit Ansatzangaben. Die Syntaxreferenz trennt
aufeinanderfolgende Gruppen und Gruppen am gleichen Ansatz. Das braucht
konkrete Parserbeispiele, bevor ein Importadapter darauf aufbaut; es ist noch
kein bestätigter Compilerfehler. Außerdem nennt der Quick Start einen
Häkelnadelwechsel als Kommentar, den der Renderer nicht auswertet. Für
Crochet.AI müssen physisch relevante Änderungen explizit gebundene Parameter
sein, falls sie in eine Vorhersage eingehen sollen.
[Quick Start](https://yarnify3d.com/docs/getting-started/quick-start).

**ESTABLISHED, dokumentierte Einschränkung:** Mehrere Ansatz-/Schlaufentechniken
sind als WIP bezeichnet und werden laut Referenz noch nicht in der 3D-Darstellung
berücksichtigt. Auch Spezialmaschen sind offen. Gleichzeitig meldet v0.20.0
Graphvalidierung und verbesserte Ring-/Rundengeometrie. Alte WIP-Markierungen und
neuere Releaseangaben müssen pro Technik praktisch abgeglichen werden; daraus
folgt kein pauschales Urteil über den aktuellen Compiler.
[Maschenreferenz](https://yarnify3d.com/docs/crochet-syntax/stitch-types),
[Release v0.20.0](https://yarnify3d.com/changelog/engine-improve-and-block-mode-visual-and-pdf-export).

**ESTABLISHED, Teile:** v0.24.0 beschreibt unabhängige Fundamente, Unterstützung
und Vorschauen pro Teil. v0.27.0 ergänzt frei positionierbare Teile.
**HYPOTHESIS:** Damit lässt sich ein montiertes Ergebnis verständlich präsentieren.
Die Quellen belegen jedoch keine maschinell geprüften Nähverbindungen oder
nahtlose Topologie allein durch räumliches Zusammenschieben.
[Unabhängige Teile](https://yarnify3d.com/changelog/independent-pattern-parts),
[Teileanordnung](https://yarnify3d.com/changelog/multilingual-parts-in-3d-and-block-mode).

**ESTABLISHED, Physik:** v0.23.0 beschreibt gleiche Maschenlängen wie im Layout
und weiche Bindung der Maschen an Ruhepositionen.
**HYPOTHESIS:** Das begünstigt eine stabile interaktive Vorschau. Aus dieser
Beschreibung folgen keine kalibrierten Materialparameter, Fehlergrenzen oder
unabhängige Vorhersage der erreichbaren Form. Ein solcher Nachweis wurde hier
nicht gefunden. Der technische Algorithmus bleibt ohne Code-/Methodenbeleg
unbekannt. [Physik-Release](https://yarnify3d.com/changelog/physics-alignment-and-preview-polish).

**ESTABLISHED, Speicherung/Geschäftsmodell:** Die Dokumentation nennt zehn
gespeicherte Muster und beschreibt höhere Pläne als noch nicht verfügbar; sie
warnt vor endgültiger Musterlöschung. Die Nutzungsbedingungen beschreiben
einen Marktplatz für digitale Muster. Aktuelle zahlbare Tarife, Transaktionen
und kommerzielle Traktion wurden nicht nachgewiesen.
[Musterverwaltung](https://yarnify3d.com/docs/patterns/managing-patterns),
[Nutzungsbedingungen](https://yarnify3d.com/terms).

## Vergleich mit unserem tatsächlichen Stand

| Bereich | Crochet.AI im gelesenen Arbeitsstand | Produktfolge |
| --- | --- | --- |
| Repräsentation | Versioniertes CrochetIR mit expliziten Ansatzstellen, Ereignissen, Frontiers, Garn-/Farbzuständen und unabhängigem SemanticValidator | Geeignete Basis für nachvollziehbare Maschenauswahl und Diagnosen; noch keine fertige Benutzeroberfläche. |
| Text | Pattern V1: ein unverzweigter Bestandteil; CHAIN/SC, binäre SC-Zu-/Abnahmen, Garnwechsel, Reihen/Runden und Abschluss | Drei Terminologieprofile existieren; die umgebenden Templates sind Englisch. Keine vollständige deutsche Anleitung oder allgemeiner Freitextimport. |
| Erzeugung | Enger analytischer SC-Kandidat und begrenzte Zählsuche | Allgemeine Mesh-, geodätische, Frontier-, Kleidungs-, Flach- und Lace-Erzeugung bleibt offen. |
| Vorschau/Physik | Unabhängige physische Projektion und experimentelle Stretch-/Shear-/Bending-Arbeit; enger unterstützter Umfang | Keine ausgelieferte 3D-Editor-/Häkel-App. Kein kalibrierter physischer Genauigkeitsnachweis. |
| Teile/Farben | Allgemeines IR kann mehr ausdrücken als aktueller Export-/Generatorpfad | Montage, Verzweigung und Mehrfarbigkeit dürfen nicht aus Schemafähigkeit als durchgängige Produktfähigkeit abgeleitet werden. |
| Prüfung | Explizite Ablehnung und Teilprüfungen vorhanden; Gesamtpipeline und Release offen | Keine Behauptung vollständiger V0–V10-Abnahme oder physischer Validierung. |

Lokale Belege: [Produktvertrag](../PRODUCT.md), [CrochetIR](../CROCHET_IR.md),
[Pattern V1](../PATTERN_FORMAT_V1.md), [Runtime](../BACKEND_RUNTIME.md),
[Backend-Abnahme](../BACKEND_ACCEPTANCE_PLAN.md),
[Forward Model](../FORWARD_MODEL.md), [Materialmodell](../MATERIAL_MODEL.md).
Der README-Bootstraptext ist bezüglich experimenteller Forward-Arbeit weniger
präzise als die aktuellen Runtime-/Abnahmedokumente.

## Empfehlungen für die spätere Produktphase

Alle folgenden Punkte sind **FUTURE**, mit begründeter Priorität. Es gibt hier
keine Vertragsänderung, Implementierung oder Freigabe eines neuen Meilensteins.

| Priorität | Empfehlung | Warum und Bedingung |
| --- | --- | --- |
| P1 | Zwei Eingänge: Design erzeugen sowie unterstützte Anleitung importieren/bearbeiten | Unterschiedliche Nutzerziele bedienen, beide in validiertes CrochetIR überführen. Ein Import muss unbekannte Techniken und Mehrdeutigkeit erklären und ablehnen. |
| P1 | Auswahl zwischen Text, Masche und Konstruktion synchronisieren | Zeigen, wo eingestochen wird, welche Schleifen entstehen und wo die Anweisung steht. Aus kanonischen Referenzen ableiten, nicht aus räumlicher Nähe oder freier Prosa. |
| P1 | Häkelmodus mit Maschen-/Anweisungs-/Rundenwechsel | Große bedienbare Tasten, rückgängig machbarer Fortschritt, Notizen und Fortsetzen nach Neustart. Offline-Nutzung und eine eigenständige mobile App als spätere Produktanforderung prüfen. |
| P1 | Einfach verständliche Evidenz und Diagnosen | Aktuelle Ursache und nächste mögliche Handlung zeigen. Letzte gültige Vorschau sichtbar als veraltet markieren; fehlgeschlagene neue Änderungen dürfen keinen aktuellen Erfolg suggerieren. |
| P1 | Endbild, Zwischenzustand und Montage unterscheiden | Einzelteile und Ansatz-/Nähstellen erklären. Räumlich platzierte Augen dürfen keinen automatisch geprüften Anschluss behaupten. |
| P2 | Unterstützte Fähigkeiten je Pipeline-Stufe zeigen | Separat sichtbar: interpretierbar, semantisch prüfbar, exportierbar, darstellbar, physisch simulierbar. Stufenbezogene Fehler erhalten. |
| P2 | Material-/Maschenprobe in reale Größenänderungen einbeziehen | Separaten Maschen-/Reihenabstand und Unsicherheit verwenden. Materialbedingte Neuplanung ist eine neue versionierte Konstruktion; physische Kalibrierung bleibt Pflicht. |
| P2 | Klarer PDF-Export mit Montage, Farbwechseln und Versionsbezug | Menschlich lesbarer Text plus getrennte Herkunft/Evidenz. Bestehenden semantischen Round Trip für unterstützte Sprache erhalten; PDF allein beweist keine Semantik. |
| P3 | Visueller Editor, danach Community | Erst verlustfreie Wechsel und sichere Bearbeitung lösen. Ein Marktplatz braucht nachvollziehbare Rechte, Moderation und Kennzeichnung physisch getesteter Muster; er löst keine Backend-Lücke. |

Ein Schrittzähler braucht getrennte Begriffe: ausgeführte Aktion,
verbrauchte Ansatzstellen und resultierende Schleifen sind bei Zu-/Abnahmen
verschiedene Größen. Die Benutzeranzeige darf variieren, der kanonische
Loop-/Frontier-Zustand und exportierte Gesamtzahlen dürfen es nicht.

Eine wiederaufgenommene Häkel-Session sollte an einen konkreten
Konstruktionsstand gebunden sein. Nach einer Musteränderung muss sie Konflikte
erkennen statt einen alten Cursor still auf andere Maschen zu setzen.
Darstellungs- und Sessiondaten bleiben außerhalb der kanonischen Semantik.
Das ist eine Architekturempfehlung, kein jetzt eingeführter API-Vertrag.

Eine schnelle, formgebundene Vorschau kann zusätzlich hilfreich sein. Sie muss
als illustrative Ansicht bezeichnet werden. Im unabhängigen Forward Model
bleiben Zielkoordinaten, Generator-Einbettung und formgebundene Anker verboten.
Ergebnisse interaktiven Ziehens dürfen weder V6 ersetzen noch dessen Cache oder
Abnahmeevidenz verändern. Kamera-/Montagetransformationen sind keine Naht- oder
Garnverbindungen.

Die visuelle Ausgestaltung entsteht eigenständig nach den Nutzerregeln.
Funktionale Ideen benötigen keine Übernahme ihrer Farben, Schrift, runden
Karten, Schatten oder Dekoration. Für Mobilgeräte sind Vorschau und Anweisung
nebeneinander bzw. umschaltbar zu erproben; Bedienelemente und Anleitungen müssen
auch ohne Farbunterscheidung, Gerätesensor und präzises Drag-and-drop nutzbar sein.

## Offene Nachweise und passende nächste Versuche

| Frage | Originaler Versuch / Abnahmeziel | Zuständigkeit und betroffene Grenze |
| --- | --- | --- |
| Wie gut ist ihr tatsächlicher Funktionsumfang? | Später mit vorhandener oder separat autorisierter Anmeldung selbst erstellte Ring-, Zu-/Abnahme-, Farb- und Zweiteilbeispiele prüfen; Text/Block/PDF/Live vergleichen. Keine Fremdmuster als Goldens. | Produktresearch; keine Solverfreigabe. |
| Hilft synchronisierte Auswahl beim Häkeln? | Nach Backend-Abnahme denselben eigenen kleinen Entwurf mit PDF und Häkelmodus bearbeiten lassen; Suchfehler, verlorene Position und Wiederaufnahme beobachten. Messplan vorab festlegen. | UX/Export; neues Sessionkonzept separat reviewen. |
| Ist ein Moduswechsel verlustfrei? | Eigene unterstützte Beispiele einschließlich Wiederholungen, Garnrückkehr und expliziten Ansätzen durch Text/visuellen Modus zurückführen; kanonische semantische Bytes vergleichen. Unbekanntes ausdrücklich ablehnen. | Parser/Export; PatternParseContext und Zertifizierung nicht still erweitern. |
| Erzeugen interaktive Ansichten falsche Physikevidenz? | Kamera, Drag-Anker und Teilanordnung variieren; unabhängige Forward-Eingaben/-Ergebnisse dürfen davon nicht beeinflusst werden. Bei neuer Konstruktion neu prüfen. | Forward/Verification; Review von Trust Boundary und Common-Mode-Risiken. |
| Ist die erzeugte Form tatsächlich richtig? | Eigene physische Proben mit gemessenen Maschen-/Reihenabständen, Belastung, Maßen und separaten Holdouts; Unsicherheit und Fehlerraten berichten. Keine Prüfung durch bloße Ähnlichkeit zum Render. | Material/Verification; RQ-102/103/104/105 und B4/B5/B11 bleiben offen. |

Hier werden keine neuen numerischen Toleranzen oder Erfolgsquoten festgelegt.
Jeder spätere Versuch braucht vorab einen begründeten Mess-/Budgetplan und
verantwortliche Kalibrierung. Keine ADR, Fixture oder bestehende Golden-Datei
wurde durch diesen Vergleich geändert.

## Quellen- und Lizenzstatus

Alle oben verlinkten Webseiten wurden am **2026-10-04** geprüft. Anbieter:
Yarnify3D. Die Einführung nennt fünf Entwicklerstudierende und ein EPITECH-Projekt
des Jahrgangs 2027; das ist eine Selbstauskunft, kein Launchdatum. Alpha-/Beta-
Bezeichnungen sind nicht einheitlich. Die Seiten sind veränderlich, ohne hier
verifizierte Quellrevision; die datierten Releases helfen bei der Einordnung.

Zusätzliche geprüfte Primärseiten: [Docs-Index](https://yarnify3d.com/docs),
[Quick Start](https://yarnify3d.com/docs/getting-started/quick-start),
[öffentlicher Marketplace](https://yarnify3d.com/marketplace),
[Datenschutz](https://yarnify3d.com/privacy).
Nutzungsbedingungen und Datenschutzerklärung sind vorhanden. Das ist kein Audit
ihrer juristischen Angemessenheit oder tatsächlichen Datenverarbeitung.

Kein Anbieter-Repository, Algorithmuscode, Dataset oder wiederverwendbares
Asset mit kompatibler Lizenz wurde in dieser Recherche verifiziert. Die
Nutzungsbedingungen beanspruchen Rechte am Dienst und dessen Originalinhalten.
**ENGINEERING DECISION: kein Code-, Muster-, Text-, Bild- oder Asset-Reuse.**
Öffentliche Beschreibungen werden knapp attribuiert; Vorschläge sind eigene
Produkt-/Architekturarbeit. Keine Kooperation, Integration oder externe
Korrektheitsreferenz beschlossen.

Validierung dieses Records: Quellenabgleich, visueller Bild-/Browsercheck,
lokale Vertragsprüfung und getrennte read-only Repository-Erkundung. Keine
App-Funktion hinter Login, kein physischer Test und keine Backend-Testausführung
für diese reine Dokumentationsänderung. Backend-Abnahme bleibt offen.
