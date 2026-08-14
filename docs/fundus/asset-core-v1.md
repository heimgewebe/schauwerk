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
- Ein Build bindet Assetmanifest, Recipe, alle verwendeten Quellhashes, Toolchain und exakte Outputhashes.
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

## Composition v2

`schauwerk-fundus-recipe.v1` bleibt vollständig unterstützt und beschreibt weiterhin genau eine Quelle, eine Transformation und einen Output. `schauwerk-fundus-recipe.v2` ergänzt eine geordnete Liste aus ein bis acht Operationen. Jede Operation bindet weiterhin **genau eine** Asset-Quellrolle, **genau eine** bestehende Fundus-Transformation und **genau einen** Output. Quellrollen dürfen für Fan-out mehrfach verwendet werden; Outputrollen und Outputdateinamen müssen innerhalb des Recipe eindeutig sein.

Damit kann ein Asset beispielsweise gleichzeitig

```text
trace_source   → sanitize_svg      → mask.svg
texture_source → raster_normalize  → texture.png
```

bauen. Form und Material bleiben getrennte Produktionsbytes und können unabhängig konsumiert werden. Composition v2 führt bewusst **kein** implizites Blending, Mask-Compositing oder sonstiges Multi-Input-Pixelverfahren ein. Eine spätere echte Kompositionsoperation braucht einen eigenen expliziten Transformvertrag, eigene Parameter und eigene technische Acceptance-Regeln.

Ein v2-Build verwendet `schauwerk-fundus-build.v2`, bindet die tatsächlich benötigten Quellen in der Reihenfolge ihrer ersten Verwendung und bindet jeden Output zusätzlich an seine `source_role`. Generative Image-Brief-Digests bleiben an der jeweiligen Quelle erhalten. Die technische Toolchain-Evidenz wird pro Operation aufgezeichnet. Preview kann alle SVG-/PNG-Outputs eines Builds gemeinsam und ohne Netzabhängigkeit darstellen.

Nach visueller Acceptance erzeugt ein v2-Build `schauwerk-fundus-package.v2`. Jedes Package-File trägt seine `source_role`; vorhandene generative Briefbindungen werden als rollenbezogene `source_image_briefs` weitergetragen und vor Packaging erneut gegen die exakten Source-/Outputrollen geprüft. Die bestehende Acceptance v1 muss dafür nicht versioniert werden: sie bindet bereits Build-Digest und die vollständige Liste der Output-Digests.

## SVG-Profile

`svg.mask.v1` erlaubt nur passive geometrische SVG-Primitiven. `svg.decorative.v1` ergänzt lokale Gradienten, Clips und Masks. Beide Profile verbieten Scripts, Eventhandler, Stylesheets, `foreignObject`, externe URLs, Daten-URLs, Fonts, fremde Namespaces sowie DOCTYPE-/ENTITY-Deklarationen. Sanitizing konkretisiert damit die Active-Resource-Grenze aus der kanonischen Publication-Regel und geschieht vor einer möglichen späteren Optimierung. Zusätzlich gelten Größen-, Tiefen-, Element- und Pfadbudgets.

## Raster- und Trace-Profile

`raster.png.rgba.v1` normalisiert PNG, JPEG und WebP mit Pillow 12.2.0 zu metadatafreiem RGBA-PNG unter festen Pixel- und Outputbudgets. `trace.vtracer.color.v1` nutzt VTracer 0.6.15 mit vollständig expliziten Parametern und `path_precision=3`; seine Ausgabe wird erst nach Dimensionsbindung und anschließendem `svg.decorative.v1`-Sanitizing zu einem Fundus-Build. Für transparente Line-Art extrahiert `trace.vtracer.alpha-mask.v1` deterministisch den Alpha-Kanal, binarisiert bei Alpha 8, traced im Binary-Modus und muss anschließend `svg.mask.v1` erfüllen. Damit werden feine Construction-Master nicht als tausende Farb-/Transparenzstufen vektorisiert. Der Traceadapter ist optional und darf die Core-Gesundheit nicht bestimmen.

## Bildoperationen

Generierte oder generativ bearbeitete wiederverwendbare Quellen folgen zusätzlich dem normativen [Image Operations v1](image-operations-v1.md). Vor der Bildoperation wird ein digestierbarer Image Brief vorbereitet und immutable hinterlegt; `generated`- und `edited`-Quellen müssen dessen SHA-256 beim Ingest binden. Ein generatives Edit bindet zusätzlich seine exakte Eingangsrevision. Build und Package validieren diese Bindung erneut.

## Lifecycle

```text
source file(s)
   ↓ ingest
content object(s)
   ↓ asset + recipe
build
   ↓
single-asset preview / family review bundle
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
schauwerk fundus review build botanical.laurel --output-dir /tmp/laurel-review --json
schauwerk fundus accept botanical.laurel.corner --build DIGEST --reviewer human:alexander --decision accepted --json
schauwerk fundus package botanical.laurel.corner --build DIGEST --acceptance DIGEST --json
schauwerk fundus package-verify path/to/package --json
schauwerk fundus consumer-lock path/to/package --json
schauwerk fundus consumer-check path/to/fundus-consumer-lock.json path/to/package --json
```

## Package- und Consumer-Vertrag

Der [Package Consumer Contract v1](package-consumer-contract-v1.md) ergänzt eine runtime-unabhängige, read-only Package-Verifikation und ein separates digestgebundenes `schauwerk-fundus-consumer-lock.v1`-Metadatum. Das immutable Package wird dabei nicht nachträglich verändert. Schauwerk schreibt den Lock ausschließlich create-or-verify in den eigenen Fundus-State; Grabowski übernimmt Package und Lock später unter Zielrepo-Autorität.

## Reviewflächen

Der bevorzugte Standardpfad ist [Fundus Review Pages v1](review-pages-v1.md): ein providerneutrales, statisches und digestgebundenes Review-Bundle für ganze Assetfamilien. Der Default-Renderer erlaubt direkten Variantenvergleich; ein kleiner sicherer Consumer-Fragment-Vertrag kann lokale Fixtures und projektspezifische Komposition einbringen, ohne projektspezifische Semantik in den Fundus-Core zu ziehen. Review-Bundles erzeugen weder Acceptance noch Package.

Fundus bleibt auch dann Miro-unabhängig, wenn Builds zusätzlich auf eine kollaborative Oberfläche projiziert werden. [Miro Fundus Atelier v1](../operators/miro-fundus-atelier-v1.md) ist ein optionaler Adapter für Workshops, freie Anordnung und Kommentare. Er liegt vollständig auf der Miro-Seite der Architektur und ist nicht der kanonische Standard-Reviewpfad.

## Nicht-Ziele V1

Keine Bildgenerierungs-API, kein Downloads-Watcher, keine Datenbank, kein CDN, kein Git LFS, keine Embeddings, keine semantische Suche und kein verpflichtender Desktopeditor. Nach dem reproduzierbaren Adapterbenchmark ist Pillow der deterministische Raster-Core; VTracer 0.6.15 ist der optionale, nachgelagert sanitisierte Traceadapter. Potrace, rembg, Inkscape und weitere Vendorpfade bleiben außerhalb des Core, bis eigene Evidenz ihren Nutzen belegt. Siehe `adapter-benchmark-v1.md`.

## Abnahme

V1 ist belastbar, wenn ein neutrales SVG-Fixture über getrennte State-Roots denselben Build und dasselbe Package erzeugt, aktive SVG-Inhalte fail-closed abgewiesen werden, die Fundus-Importgrenze Miro-frei bleibt und ein gebautes Wheel ohne Source-Tree alle Fundus-Schemas sowie Build, Review und Packaging ausführen kann. Composition v2 ergänzt dazu den Nachweis, dass ein Asset mehrere getrennte Quellen deterministisch in mehrere getrennte Outputs überführen kann, ohne v1-Digests oder v1-Packages zu verändern. Das erzeugte Review-Bundle und das Consumer-Package bleiben ohne laufende Schauwerk-Runtime nutzbar. Reale Projektpiloten bleiben getrennte Consumer-Slices und begründen keine projektspezifische Core-Semantik.
