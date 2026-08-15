# Fundus Golden Path v1

Stand: 15. August 2026

Dieser Beleg führt genau ein neues, nicht aus Legacy-Material umdeklariertes Asset bis zur digestgebundenen Preview. Visuelle Acceptance, Packaging und Consumer-Integration bleiben absichtlich gesperrt, bis ein Mensch den exakten Build visuell akzeptiert.

## Asset

- Asset: `botanical.concave-frame.corner.v1`
- Familie: `botanical.concave-frame`
- Operation: `generate`
- Source-Rolle: `trace_source`
- Origin: `ai-generated:chatgpt-svg-imagemagick:botanical-concave-frame-corner-v1`
- Recipe: `vtracer-alpha-mask-v1`
- `mirror_safe`: `false`
- `rotate_safe`: `false`
- `recolor_safe`: `true`
- `mask_safe`: `true`

## Digestbindungen

- Image Brief: `ce3af1752484011247281f244c4f7121ca4612bd84694731fab3b515396a2762`
- Source-Master: `71db96cafaf98b9ec330401be6c3cac232d8bd3a2337140692c17e9ad6dc9fcd`
- Assetmanifest: `75df6fcb24b9874820ddf10a2220423197d82074603b40da7a60a1840b76e016`
- Recipe: `6289bee53e00f4c70c8104126661a839e8209b480436502785786a72667093cb`
- Build: `608fca2f2ba23fd0e64eb7d9fbc55346be23d7ff11c3a32ba737e392896a77d1`
- Output `mask.svg`: `d05245fa35e5c52e784fd565c88547d2d9dfc0708b88ad871797e680c9a571a1`
- Preview: `dab0e9a33b351f6ef15ebbce1ec7c4b92d7b10dd8797bfe8c8ce383e275a4145`

## Technische Evidenz

- Ingest bindet `source_mode=generated` an den vorbereiteten Image-Brief-Digest und deklariert ChatGPT als generativen Ursprung; ImageMagick ist der lokale Raster-Renderer.
- Source-Master: PNG, 1536 × 1536, Alpha vorhanden und für den Mask-Trace nutzbar.
- Build: erfolgreich mit Pillow `12.2.0`, VTracer `0.6.15`, `trace.vtracer.alpha-mask.v1` und `svg.mask.v1`.
- Drift-Check: `clean`.
- Reproduktion in temporärem Fundus-State: gleicher Build-Digest, gleiche Output-Digests, gleiche Toolchain.
- Preview: selbständig und ohne Netzwerkabhängigkeiten erzeugt.
- Der exakte Source-Master bleibt zusätzlich außerhalb des Object Stores erhalten, solange die Restore-Evidenz für den nach diesem Ingest veränderten Fundus-Bestand noch nicht erneuert ist.

## Im Golden Path gefundene Lücke

Der erste Build zeigte, dass das generische SVG-Attributlimit von 16.384 Zeichen auch auf `path d` angewendet wurde, obwohl für Pfaddaten bereits ein eigenes Gesamtbudget von 200.000 Zeichen existiert. Der reale VTracer-Output bestand nur aus zwei Pfaden und 20,7 KB SVG, enthielt aber einen legitimen `d`-Wert mit 19.702 Zeichen.

Der Fix lässt ausschließlich `path d` vom generischen Attributlimit ausnehmen. Pfaddaten bleiben durch Zeichenalphabet, Gesamtpfadbudget, Gesamtdateigröße, Elementzahl, Tiefe und SVG-Sicherheitsprofil begrenzt. Normale Attribute behalten das 16.384-Zeichen-Limit.

## Noch nicht etabliert

- keine visuelle Acceptance;
- kein freigegebenes Produktionsasset;
- kein immutable Package;
- kein Consumer Lock;
- keine Integration in Hall of Memory oder ein anderes Fremdrepository;
- keine aktuelle Restore-Evidenz für den durch diesen Ingest erweiterten Object Store.

Diese Punkte dürfen nicht aus der erfolgreichen technischen Pipeline abgeleitet werden.
