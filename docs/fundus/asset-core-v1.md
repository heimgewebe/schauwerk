---
id: schauwerk-fundus-asset-core-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Asset Core v1
summary: Miro-independent source, build, review and package lifecycle for reusable visual components.
---

# Schauwerk Fundus Asset Core v1

## Entscheidung

Der Fundus ist ein Miro-unabhängiger Modulith innerhalb von Schauwerk. Er verwaltet wiederverwendbare visuelle Bauteile, ohne Miro, OAuth, Boards, Providerzustand oder Cross-Repo-Mutationen zu benötigen. Die Grenze ist absichtlich extrahierbar: `src/schauwerk/fundus/` darf keine Miro- oder Operatormodule importieren.

## Autorität

- Git besitzt Asset-, Family- und Recipe-Semantik.
- Der private content-addressed Store hält digestgeprüfte unveränderte importierte Bytes, bleibt aber bis zum bewiesenen Backup-/Restore-Vertrag nicht alleinige Masterautorität.
- Ein Import-Receipt dokumentiert deklarative Provenienz; es authentifiziert keinen Generator oder Urheber.
- Ein Build bindet Assetmanifest, Recipe, Quellhash, Toolchain und exakte Outputhashes.
- Eine visuelle Acceptance bindet eine deklarierte Entscheidung an genau einen Build. `reviewer_identity_authenticated=false` verhindert eine überzogene Identitätsbehauptung.
- Ein Package enthält nur akzeptierte Outputs und hat keine Laufzeitabhängigkeit von Schauwerk.
- Grabowski, nicht Schauwerk, integriert ein Package in fremde Repositories.

## Source-Store

Standardpfad:

`~/.local/share/schauwerk/fundus/objects/sha256/`

Ingest ist create-only und hashgebunden. Dateizugriffe über die Fundus-Vertrauensgrenze öffnen die vollständige Verzeichniskette descriptor-relativ mit No-Follow-Semantik, begrenzen Reads am geöffneten Descriptor und lehnen Symlinks, Hardlinks, fremde Eigentümer sowie gruppen- oder weltbeschreibbare Quellen ab. Unterstützte V1-Quellformate sind SVG, PNG, JPEG und WebP. Originaldateien außerhalb des Stores werden nicht automatisch gelöscht. Der Store gilt bis zu einem gesondert bewiesenen Backup-/Restore-Vertrag ausdrücklich nicht als alleinige Masterautorität.

## Assetmodell

Ein Asset kombiniert Rollen statt einer starren Raster-/Vektor-Schublade.

Quellrollen:

- `original`
- `trace_source`
- `texture_source`
- `reference`

Outputrollen:

- `vector`
- `mask`
- `outline`
- `raster`
- `texture`
- `preview`

Semantische IDs bleiben menschenlesbar, zum Beispiel `botanical.laurel.corner`; konkrete Revisionen sind immer digestgebunden.

## SVG-Profile

`svg.mask.v1` erlaubt nur passive geometrische SVG-Primitiven. `svg.decorative.v1` ergänzt lokale Gradienten, Clips und Masks. Beide Profile verbieten Scripts, Eventhandler, Stylesheets, `foreignObject`, externe URLs, Daten-URLs, Fonts, fremde Namespaces sowie DOCTYPE-/ENTITY-Deklarationen. Sanitizing konkretisiert damit die Active-Resource-Grenze aus der kanonischen Publication-Regel und geschieht vor einer möglichen späteren Optimierung. Zusätzlich gelten Größen-, Tiefen-, Element- und Pfadbudgets.

## Raster- und Trace-Profile

`raster.png.rgba.v1` normalisiert PNG, JPEG und WebP mit Pillow 12.2.0 zu metadatafreiem RGBA-PNG unter festen Pixel- und Outputbudgets. `trace.vtracer.color.v1` nutzt VTracer 0.6.15 mit vollständig expliziten Parametern und `path_precision=3`; seine Ausgabe wird erst nach Dimensionsbindung und anschließendem `svg.decorative.v1`-Sanitizing zu einem Fundus-Build. Für transparente Line-Art extrahiert `trace.vtracer.alpha-mask.v1` deterministisch den Alpha-Kanal, binarisiert bei Alpha 8, traced im Binary-Modus und muss anschließend `svg.mask.v1` erfüllen. Damit werden feine Construction-Master nicht als tausende Farb-/Transparenzstufen vektorisiert. Der Traceadapter ist optional und darf die Core-Gesundheit nicht bestimmen.

## Bildoperationen

Generierte oder generativ bearbeitete wiederverwendbare Quellen folgen zusätzlich dem normativen [Image Operations v1](image-operations-v1.md). Vor der Bildoperation wird ein digestierbarer Image Brief vorbereitet und immutable hinterlegt; `generated`- und `edited`-Quellen müssen dessen SHA-256 beim Ingest binden. Ein generatives Edit bindet zusätzlich seine exakte Eingangsrevision. Build und Package validieren diese Bindung erneut.

## Lifecycle

```text
source file
   ↓ ingest
content object
   ↓ asset + recipe
build
   ↓
preview
   ↓ visual decision
acceptance
   ↓
immutable package
   ↓
Grabowski target-repo integration
```

CLI:

```bash
schauwerk fundus doctor --json
schauwerk fundus brief image-brief.json --json
schauwerk fundus ingest artwork.svg --origin chatgpt-images:ornament --source-mode generated --image-brief image-brief.json --rights-status owned --json
schauwerk fundus inspect botanical.laurel.corner --json
schauwerk fundus build botanical.laurel.corner --json
schauwerk fundus preview botanical.laurel.corner --json
schauwerk fundus accept botanical.laurel.corner --build DIGEST --reviewer human:alexander --decision accepted --json
schauwerk fundus package botanical.laurel.corner --build DIGEST --acceptance DIGEST --json
```

## Nicht-Ziele V1

Keine Bildgenerierungs-API, kein Downloads-Watcher, keine Datenbank, kein CDN, kein Git LFS, keine Embeddings, keine semantische Suche und kein verpflichtender Desktopeditor. Nach dem reproduzierbaren Adapterbenchmark ist Pillow der deterministische Raster-Core; VTracer 0.6.15 ist der optionale, nachgelagert sanitisierte Traceadapter. Potrace, rembg, Inkscape und weitere Vendorpfade bleiben außerhalb des Core, bis eigene Evidenz ihren Nutzen belegt. Siehe `adapter-benchmark-v1.md`.

## Abnahme

V1 ist belastbar, wenn ein neutrales SVG-Fixture über getrennte State-Roots denselben Build und dasselbe Package erzeugt, aktive SVG-Inhalte fail-closed abgewiesen werden, die Fundus-Importgrenze Miro-frei bleibt und ein gebautes Wheel ohne Source-Tree alle Fundus-Schemas sowie den kompletten Lifecycle ausführen kann. Das erzeugte Consumer-Package bleibt ohne Schauwerk-Runtime nutzbar. Der spätere Hall-of-Memory-Pilot ist ein getrenntes Zielrepo-Slice.
