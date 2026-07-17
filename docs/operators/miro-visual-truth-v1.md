# Miro Visual Truth v1

Stand: 17. Juli 2026

## Zweck

Visual Truth bindet eine authentifiziert aufgenommene Miro-Ansicht an einen exakten, zweimal identisch gelesenen und sanitisierten Board-Snapshot. Der Vertrag schließt die Lücke zwischen strukturierter Provider-Rücklesung und der sichtbaren Miro-Darstellung.

Er ersetzt weder den Miro-Readback noch eine menschliche Gestaltungsprüfung. Eine Bedienerattestation ist ausdrücklich kein kryptografischer Authentifizierungsbeweis.

## Eingaben

`schauwerk miro visual-truth create` erwartet:

1. einen Schauwerk-Snapshot mit `repeatability_verified=true`, `verified_reads=2`, `sanitized_references=true` und einem 64-stelligen `content_digest`;
2. eine PNG-, JPEG- oder WebP-Aufnahme;
3. einen Kontext nach `schauwerk-miro-visual-truth-context.v1`;
4. ein noch nicht vorhandenes Receipt-Ziel.

Der Board-Referenzdigest wird nicht vom Bediener übernommen. Die CLI löst den Alias über die lokale, owner-only Board-Allowlist auf und leitet daraus den erwarteten Digest ab.

```text
schauwerk miro visual-truth create \
  snapshot.json \
  capture.png \
  capture-context.json \
  --output visual-truth-receipt.json \
  --json

schauwerk miro visual-truth check visual-truth-receipt.json --json
```

## Prüfungen

Der Ersteller arbeitet fail-closed und prüft:

- reguläre Dateien ohne Symlinks und Hardlinks;
- begrenzte Dateigrößen;
- Bildsignatur und Abmessungen;
- Alias-, Inhaltsdigest- und Allowlist-Bindung;
- Miro-Board-URL und Providerursprung;
- Aufnahmezeitpunkt: höchstens 24 Stunden alt und höchstens fünf Minuten in der Zukunft;
- ausdrückliche Authentifizierungsattestation;
- sichtbare Marker gegen Login-, Zugriffs-, Fehler- und Nicht-Board-Seiten.

Das create-only Receipt hat Modus `0600`. Es enthält keine Board-URL und keine Board-ID, sondern nur Digests, Bildmetadaten, Zeitbindung und die Grenzen der Evidenz.

## Evidenzstärke

Belegt werden:

- der exakte Snapshotdigest;
- der exakte Bilddigest;
- der exakte Kontextdigest;
- die Allowlist-Bindung;
- das Aufnahmeformat und die Abmessungen;
- die zeitliche Nähe der Aufnahme;
- die vom Bediener erklärte authentifizierte Boardansicht.

Nicht belegt werden:

- kryptografisch bestätigte Miro-Authentifizierung;
- pixelidentische Darstellung auf anderen Geräten oder zu späteren Zeitpunkten;
- ästhetische Qualität;
- semantische Richtigkeit des sichtbaren Inhalts;
- Inhalt außerhalb des aufgenommenen Viewports.
