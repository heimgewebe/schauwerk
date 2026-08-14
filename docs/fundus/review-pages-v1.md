---
id: schauwerk-fundus-review-pages-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Review Pages v1
summary: Projektunabhängige, portable Demo-Pages für digestgebundene Fundus-Builds mit optionalem sicheren Consumer-Kontext.
---

# Schauwerk Fundus Review Pages v1

## Entscheidung

Die bevorzugte visuelle Reviewfläche für Fundus-Assets ist eine **consumer-nahe statische Demo-Page**, nicht ein bestimmter Kollaborationsprovider. Der Fundus Review-Pfad ist deshalb vollständig providerneutral und liegt innerhalb von `schauwerk.fundus`.

Er beantwortet primär die Frage:

> Wie wirkt dieser exakte Fundus-Build in einem sinnvollen Nutzungskontext?

Er beantwortet ausdrücklich nicht:

> Ist dieser Build bereits gestalterisch freigegeben?

Eine Review-Page erzeugt weder Acceptance noch Produktionspackage.

## Architektur

```text
Fundus Family
   │
   ├── Asset A → exakter Build A
   ├── Asset B → exakter Build B
   └── Asset C → exakter Build C
             │
             ▼
      Fundus Review Plan
      build-/digestgebunden
             │
             ▼
      Review Bundle
      ├── index.html
      ├── review.css
      ├── review.js
      ├── assets/*
      ├── optional fixtures/*
      └── review.json
             │
             ├── lokal öffnen
             ├── consumer-nah prüfen
             └── später optional über Schaufenster publizieren
```

Der Review-Pfad schreibt nicht in Consumer-Repositories. Ein Zielrepo darf später eine eigene Demo oder ein akzeptiertes Fundus-Package über Grabowski integrieren.

## Projektunabhängigkeit

Der Core kennt keine Hall-of-Memory-, Website-, Kunden- oder Produktsemantik. Er kennt nur:

- Fundus-Familie und Asset-IDs;
- exakte Build-Digests;
- Outputrolle, Medientyp und Output-SHA-256;
- aktuellen Fundus-Acceptance-Zustand;
- optionale lokale Review-Fixtures;
- einen kleinen sicheren Consumer-Fragment-Vertrag.

Damit kann derselbe Pfad beispielsweise verwendet werden für:

- Rahmen auf einem Beispielfoto;
- Logos auf hellen und dunklen Flächen;
- Ornamente in einer Karten- oder Headerkomposition;
- Masken auf unterschiedlichen Hintergründen;
- Texturen auf einem lokalen Mockup;
- Iconfamilien in verschiedenen Größen;
- andere zukünftige visuelle Komponenten.

Projektspezifische Gestaltung bleibt am Consumer-Rand. Schauwerk standardisiert nur den Review-Harness und dessen Beweiskette.

## Default-Renderer

Ohne Consumer-Template erzeugt `fundus review build` eine neutrale responsive Vergleichsseite. Sie enthält:

- eine Karte pro Assetvariante;
- Asset-ID, Build-Digest, Outputrolle und Acceptance-Zustand;
- 1-/2-/3-Spalten-Vergleich;
- helle, dunkle, warme und Checkerboard-Prüfflächen;
- responsive Einspaltenansicht auf kleinen Viewports.

Der Default ist absichtlich neutral. Er soll nicht versuchen, die Gestaltung des Zielprojekts nachzuahmen.

## Consumer-Template

Wenn die Wirkung erst im Nutzungskontext sinnvoll beurteilbar ist, darf der aufrufende Consumer ein lokales HTML-Fragment und optionales CSS liefern.

Der Fragment-Vertrag ist bewusst klein. Zulässig sind passive Struktur- und Bildelemente wie `figure`, `div`, `section`, `img`, `p`, `span` und einfache Hervorhebungen. Scripts, Eventhandler, Links, Formulare, eingebettete Frames, Styles im HTML und freie externe Ressourcen sind nicht Teil des Vertrags.

Verfügbare Tokens:

```text
{{ASSET_URL}}
{{ASSET_ID}}
{{BUILD_DIGEST}}
{{OUTPUT_ROLE}}
{{ACCEPTANCE_STATE}}
{{FIXTURE:<id>}}
```

`{{ASSET_URL}}` ist verpflichtend. Fixture-Tokens sind nur für explizit gebundene lokale Review-Fixtures gültig.

Beispiel eines generischen Consumer-Fragments:

```html
<figure class="product-demo">
  <img class="fixture-photo" src="{{FIXTURE:sample}}" alt="Beispielinhalt">
  <img class="product-asset" src="{{ASSET_URL}}" alt="{{ASSET_ID}}">
</figure>
```

Das zugehörige CSS darf die lokalen Elemente anordnen, aber keine `url(...)`-Ressourcen, Imports, Fonts, Data-URLs oder ausführbaren Browsermechanismen nachladen.

## Review-Fixtures

Fixtures dienen ausschließlich der visuellen Kontextualisierung. V1 akzeptiert PNG, JPEG und WebP.

Für jedes Fixture bindet `review.json`:

- semantische Fixture-ID;
- paketrelativen Dateinamen;
- Medientyp;
- SHA-256;
- Bytezahl.

Absolute Quellpfade des Consumer-Projekts gelangen nicht in das Bundle. SVG-Fixtures sind in V1 absichtlich nicht erlaubt, damit ein Consumer nicht über ein zweites aktives Vektorformat die Fundus-Sanitizing-Grenze umgeht.

## Technische Wahrheit

Vor Bundle-Erzeugung werden alle Family-Assets reproduzierbar gebaut beziehungsweise gegen einen identischen vorhandenen Build geprüft. Die Outputbytes werden unmittelbar vor dem Kopieren erneut gegen ihre Fundus-SHA-256 verifiziert.

`review.json` bindet zusätzlich:

- den deterministischen Review-Plan-Digest;
- jede Variante an Build- und Output-Digest;
- Template- und Consumer-CSS-Digest;
- alle Fixture-Digests;
- den exakten Bundle-Dateisatz mit SHA-256 und Bytezahl;
- einen Digest über das gesamte Review-Manifest.

`fundus review check` verifiziert nicht nur den äußeren Manifest-Digest, sondern auch die internen Relationen:

- Variant-Datei ↔ Output-SHA-256;
- Fixture-Datei ↔ Fixture-SHA-256;
- Variantensatz ↔ Review-Plan-Digest;
- eindeutige Asset-, Fixture- und Dateibindungen;
- exakter Dateisatz ohne Zusatzdateien;
- keine Symlinks, Hardlinks oder gruppen-/weltbeschreibbaren Dateien.

Ein semantisch verändertes Manifest wird daher auch dann abgelehnt, wenn jemand seinen äußeren `review_digest` passend neu berechnet.

## Browser- und Netzwerkgrenze

Das Bundle ist statisch und portabel. Es besitzt keine Netzabhängigkeit.

Die generierte Seite verwendet eine restriktive Content-Security-Policy. Bilder, CSS und das kleine Review-JavaScript werden ausschließlich aus dem eigenen Bundle geladen. `connect-src`, Fonts, Frames, Objects und Form-Actions sind blockiert.

Das JavaScript steuert nur lokale Reviewdarstellung wie Hintergrund und Spaltenzahl. Es schreibt keine Fundus-Entscheidung zurück.

## Acceptance-Grenze

Eine gute Darstellung auf der Review-Page ist **Reviewevidenz**, keine Acceptance.

Der kanonische Pfad bleibt:

```text
Review Bundle
   ↓ menschliche visuelle Prüfung
explizite Entscheidung für exakt einen Build
   ↓
Fundus Acceptance
   ↓
immutable Fundus Package
   ↓
Grabowski-Integration
```

Wird ein Source-Master gestalterisch verändert, entsteht weiterhin eine neue Source-Revision und eine neue Acceptance ist erforderlich.

## Publication-Grenze

`fundus review build` erzeugt ein create-only lokales Review-Bundle. Es ist kein zweites Hosting- oder Veröffentlichungscontrol-plane.

Wenn ein Review dauerhaft oder über einen stabilen Link geteilt werden soll, bleibt der bestehende Schauwerk-Schaufenster-/Publication-Vertrag fachlich zuständig. V1 enthält dafür bewusst noch keinen Adapter: Der aktuelle Schaufenster-Eingangsvertrag erwartet flache SW-012-Public-Packages und ist nicht bytekompatibel mit dem hierarchischen Review-Bundle. Diese Grenze wird nicht durch Lockerung der Publication-Sicherheitsregeln umgangen; eine spätere Anbindung braucht einen expliziten, getesteten Adapter.

## Miro

[Miro Fundus Atelier v1](../operators/miro-fundus-atelier-v1.md) bleibt als optionaler Kollaborationsadapter bestehen, wenn freies Sortieren, Kommentieren oder Workshoparbeit den zusätzlichen Provideraufwand rechtfertigt.

Für die normale visuelle Assetprüfung ist die consumer-nahe Review-Page der bevorzugte Pfad, weil sie die tatsächliche Browserwirkung direkter zeigt und keinen Miro-spezifischen Rendering-Layer zwischen Asset und Beurteilung setzt.

## CLI

Plan einer Familie prüfen:

```bash
schauwerk fundus review plan botanical.laurel --json
```

Neutrales Review-Bundle erzeugen:

```bash
schauwerk fundus review build botanical.laurel \
  --output-dir /tmp/laurel-review \
  --json
```

Consumer-nahe Review mit lokaler Fixture:

```bash
schauwerk fundus review build botanical.laurel \
  --output-dir /tmp/laurel-consumer-review \
  --template review-fragment.html \
  --css review-consumer.css \
  --fixture sample=/path/to/local-sample.png \
  --json
```

Bundle später erneut prüfen:

```bash
schauwerk fundus review check /tmp/laurel-review --json
```

## Nicht-Ziele v1

- kein WYSIWYG-Editor;
- kein universelles Weblayoutsystem;
- kein projektspezifisches Design im Fundus-Core;
- kein Hosting- oder CDN-Vertrag;
- kein Kommentarsystem;
- keine automatische Acceptance;
- kein Cross-Repo-Write;
- kein Ersatz für den realen Consumer, wenn dessen vollständiges Verhalten für die Abnahme wesentlich ist.
