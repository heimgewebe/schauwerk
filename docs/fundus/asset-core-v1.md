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

Ingest ist create-only, hashgebunden und lehnt Symlinks, Hardlinks, fremde Eigentümer sowie gruppen- oder weltbeschreibbare Quellen ab. Unterstützte V1-Quellformate sind SVG, PNG, JPEG und WebP. Originaldateien außerhalb des Stores werden nicht automatisch gelöscht. Der Store gilt bis zu einem gesondert bewiesenen Backup-/Restore-Vertrag ausdrücklich nicht als alleinige Masterautorität.

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

`svg.mask.v1` erlaubt nur passive geometrische SVG-Primitiven. `svg.decorative.v1` ergänzt lokale Gradienten, Clips und Masks. Beide Profile verbieten Scripts, Eventhandler, Stylesheets, `foreignObject`, externe URLs, Daten-URLs, Fonts und fremde Namespaces. Sanitizing geschieht vor einer möglichen späteren Optimierung. Zusätzlich gelten Größen-, Tiefen-, Element- und Pfadbudgets.

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
schauwerk fundus ingest artwork.svg --origin chatgpt --rights-status owned --json
schauwerk fundus inspect botanical.laurel.corner --json
schauwerk fundus build botanical.laurel.corner --json
schauwerk fundus preview botanical.laurel.corner --json
schauwerk fundus accept botanical.laurel.corner --build DIGEST --reviewer human:alexander --decision accepted --json
schauwerk fundus package botanical.laurel.corner --build DIGEST --acceptance DIGEST --json
```

## Nicht-Ziele V1

Keine Bildgenerierungs-API, kein Downloads-Watcher, keine Datenbank, kein CDN, kein Git LFS, keine Embeddings, keine semantische Suche, kein verpflichtender Desktopeditor und kein fest verdrahteter Raster- oder Trace-Vendor. Raster- und Traceadapter werden erst nach reproduzierbaren lokalen Benchmarks ausgewählt.

## Abnahme

V1 ist belastbar, wenn ein neutrales SVG-Fixture zweimal denselben Build und dasselbe Package erzeugt, aktive SVG-Inhalte fail-closed abgewiesen werden, die Fundus-Importgrenze Miro-frei bleibt und das Package ohne Schauwerk-Runtime konsumierbar ist. Der spätere Hall-of-Memory-Pilot ist ein getrenntes Zielrepo-Slice.
