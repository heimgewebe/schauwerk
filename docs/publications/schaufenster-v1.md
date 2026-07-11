---
id: schauwerk-schaufenster-v1
role: contract
status: active
doc_type: publication-boundary
title: SW-013 Schaufenster v1
summary: Review-bound immutable publication packages with stable local links, expiry, withdrawal and read-only delivery.
---

# SW-013 Schaufenster v1

## Zweck

Das Schaufenster veröffentlicht nicht direkt aus einer Quelle. Es übernimmt ausschließlich ein bereits bereinigtes öffentliches SW-012-Paket und verlangt davor eine eigenständige Publikationsdeklaration. Damit bleiben Quellwahrheit, interne Sprecherfassung und öffentlich ausgelieferte Fassung getrennt.

## Ablauf

```text
SW-012 public package
        │
        ▼
strict declaration ──► deterministic preview ──► review
                                                │
                                                ▼
                                   immutable version object
                                                │
                                                ▼
                                   digest-bound stable link
                                                │
                           ┌────────────────────┴───────────────────┐
                           ▼                                        ▼
                    loopback read-only                        expiry/withdrawal
```

1. `publish preview` prüft Quellmanifest, Dateien, Sichtbarkeit, Metadatenfelder und Privacy-Grenzen. Es schreibt nur eine Reviewdatei.
2. `publish release` kompiliert die Preview erneut aus der Quelle. Nur eine byte- und digestgleiche, zuvor geprüfte Preview darf freigegeben werden.
3. Die Version wird mit Modus `0555/0444` als unveränderliches Objekt abgelegt.
4. Der stabile Link wird atomar per Linux `renameat2` und Compare-and-Swap aktualisiert.
5. `publish status` prüft Link, Objekt, Dateimengen, Dateigrößen und SHA-256 neu und leitet `scheduled`, `active`, `expired` oder `withdrawn` ab. Vor `published_at` wird nichts ausgeliefert.
6. `publish withdraw` nimmt nur den stabilen Link zurück. Das unveränderliche Objekt und die Quellwahrheit bleiben erhalten.
7. `publish serve` liefert ausschließlich über `127.0.0.1`, akzeptiert nur `GET` und `HEAD` und prüft vor jeder Auslieferung erneut die Integrität.

## Deklarationsgrenze

Eine Deklaration benennt vollständig und explizit:

- Publikations-ID, stabilen Slug, Version, Ansicht und Zielgruppe;
- SHA-256, internen Digest und Revision des SW-012-Quellmanifests;
- Einstiegspunkt und exakte Dateimenge;
- erlaubte Metadatenfelder;
- jede öffentliche Quelle und deren erlaubte Felder;
- Veröffentlichungszeit, optionalen Ablauf und bei einer Folgeversion den erwarteten bisherigen Link-Digest.

Nur `visibility: public` ist zulässig. `private`, `internal`, unbekannte Werte, neue Quellen, neue Dateien oder neue Metadatenfelder blockieren die Preview.

Maschinenvertrag:

- `schemas/publication-boundary.v1.schema.json`

## Lokaler Store

```text
<store>/
  .lock
  objects/<publication-id>/<version>/
    publication.json
    bundle/<declared files>
  links/<stable-slug>.json
  receipts/release-*.json
  receipts/withdraw-*.json
```

Objekte sind unveränderlich. Stabile Links sind veränderliche, digestgebundene Zeiger. Versionswechsel und Rücknahme verwenden einen erwarteten Link-Digest; ein zwischenzeitlich veränderter fremder Link wird nicht überschrieben.

Der Elternordner von Preview-Ausgabe und Store muss bereits existieren. Sämtliche Pfadkomponenten werden ohne Symlink-Folgen geöffnet; unsichere Elternpfade brechen vor der ersten Mutation ab.

## CLI

```bash
schauwerk publish preview declaration.json \
  --source-package /path/to/public-package \
  --output preview.json \
  --json

schauwerk publish release declaration.json preview.json \
  --source-package /path/to/public-package \
  --store-root /path/to/local-store \
  --json

schauwerk publish status stable-slug \
  --store-root /path/to/local-store \
  --json

schauwerk publish withdraw stable-slug \
  --store-root /path/to/local-store \
  --expected-link-digest <sha256> \
  --reason 'controlled withdrawal' \
  --json

schauwerk publish serve \
  --store-root /path/to/local-store \
  --port 0 \
  --no-browser
```

## Sicherheitsgrenzen

- keine implizite Quelle, Datei oder Metadatenachse;
- keine internen oder privaten Quellsichten;
- keine absoluten lokalen Pfade, Providerkennungen oder geheimnisähnlichen Zuweisungen;
- keine aktiven oder externen HTML-Ressourcen;
- keine PDF-Links, Anhänge, Formulare, JavaScript-, Launch-, OpenAction-, XFA- oder RichMedia-Objekte; V1 prüft die SW-012-Manifestbindung und relevante PDF-Rohobjekte, behauptet aber ohne zusätzliche Parser-Abhängigkeit keine allgemeine semantische PDF-Inhaltsanalyse;
- keine PPTX-Notizfolien, Kommentare, Einbettungen, Makros, Custom XML oder externen Beziehungen; jedes entpackte ZIP-Mitglied wird auf sensible Pfade und Zuweisungen geprüft;
- keine stillen Overwrites;
- symlinksichere Store-Locks, atomare No-Replace-Veröffentlichung und digestgebundener Link-Compare-and-Swap;
- gemeinsamer Rollback von Link und neuem Objekt bei Fehlern nach der Umschaltung;
- read-only Status und Auslieferung verändern den Store nicht;
- Quellpaket und Miro werden nie verändert.

## Betriebsgrenze

V1 ist ein providerneutraler lokaler Publikationskern. Es gibt keinen öffentlichen Host, kein DNS, kein CDN, kein Deployment und keine Miro-Mutation. Eine spätere externe Auslieferung muss denselben Objekt-, Link-, Ablauf- und Rücknahmevertrag übernehmen und benötigt eine eng gebundene produktive Autorisierung.

Die atomaren Dateisystemoperationen erfordern Linux `renameat2` mit `RENAME_NOREPLACE` und `RENAME_EXCHANGE`. Fehlt diese Garantie, schlägt der Mutationspfad geschlossen fehl. „Atomar“ bezeichnet in V1 Prozess-, Konkurrenz- und Rollback-Atomik; eine vollständige Garantie gegen Stromausfall oder Dateisystemverlust wird nicht behauptet.

Unveränderliche Objekte sind absichtlich nicht direkt löschbar. „Unveränderlich“ bedeutet in V1: versionsgebunden, ohne Schreibbits abgelegt und vor Status oder Auslieferung vollständig hashgeprüft. Es ist kein Kernel-Immutable-Attribut. Ein Prozess unter derselben Benutzerkennung kann Schreibrechte bewusst zurücksetzen; eine danach veränderte Datei wird erkannt und nicht ausgeliefert. `flock` koordiniert kooperierende Schauwerk-Prozesse, schützt aber nicht vor einem absichtlich lockignorierenden Prozess derselben Benutzerkennung oder vor einem Dateisystemverlust.

Ein administrativer Rückbau muss zuerst die Schreibrechte des konkret ausgewählten Objektbaums wiederherstellen und darf nie pauschal fremde Store-Inhalte rekursiv verändern. V1 bietet deshalb bewusst keinen automatischen Prune-Befehl.
