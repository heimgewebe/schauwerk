---
id: schauwerk-fundus-durability-evidence-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Durability Evidence v1
summary: Provider-neutral, inventory-bound evidence that the current Fundus data-root revision survived an exact staged restore.
---

# Schauwerk Fundus Durability Evidence v1

## Zweck

Der lokale Fundus-Object-Store darf nicht allein deshalb als dauerhafte Masterautorität gelten, weil Dateien lokal vorhanden sind. Durability Evidence v1 bindet einen extern erzeugten Restore-Beleg an **genau das aktuell sichtbare Fundus-Inventar**.

Der Fundus-Core bleibt dabei providerneutral. Er führt keinen Backup-Job aus, öffnet keine Netzwerkverbindung und kennt weder Restic noch einen konkreten Remote-Store. Er liest ausschließlich einen externen Receipt und vergleicht dessen Inventarbindung mit dem heutigen Data-Root.

## Inventarvertrag

Das Inventar verwendet `schauwerk-fundus-inventory.v1`.

Für jede reguläre Datei unter dem Fundus-Data-Root wird rekursiv und lexikografisch nach Pfad erfasst:

- relativer POSIX-Pfad;
- Bytegröße;
- SHA-256 der Datei.

Symlinks und spezielle Dateien sind verboten. Beim Hashen werden Pfadidentität, Dateigröße und `mtime_ns` vor/nach dem Lesen geprüft. Der Inventar-Digest ist SHA-256 über die kanonische JSON-Repräsentation von:

```json
{
  "schema_version": "schauwerk-fundus-inventory.v1",
  "files": [
    {"path": "...", "bytes": 123, "sha256": "..."}
  ]
}
```

Das Durability-Receipt bindet zusätzlich `file_count` und `total_bytes`.

## Evidence-Receipt

Ein Producer darf erst nach einem erfolgreich abgeschlossenen Restore-Gate ein `schauwerk-fundus-durability-evidence.v1` erzeugen. V1 akzeptiert ausschließlich:

`verification=staged_restore_exact_snapshot`

Das bedeutet mindestens:

1. vor dem Backup wird das exakte Fundus-Inventar eingefroren;
2. genau der erzeugte Snapshot wird identifiziert;
3. Fundus wird aus genau diesem Snapshot in ein getrenntes Staging-Verzeichnis restauriert;
4. das restaurierte Inventar wird vollständig gegen das eingefrorene Inventar verglichen;
5. erst nach erfolgreicher Gleichheit wird das externe Receipt aktualisiert.

Das Receipt enthält:

- Inventaralgorithmus und Inventar-SHA-256;
- Dateizahl und Gesamtbytes;
- Verifikationsmodus;
- einen generischen `producer`;
- einen opaken `evidence_ref`;
- `verified_at` mit Zeitzone;
- einen Eigendigest `receipt_digest` über alle übrigen Felder.

`producer` und `evidence_ref` werden vom Fundus-Core **nicht interpretiert**. Ein Restic-Snapshot, ein anderer Backupdienst oder ein späterer eigener Broker können denselben Vertrag erfüllen.

## Ablagegrenze

Der Beleg muss außerhalb des zu attestierenden Fundus-Data-Roots liegen. Standardpfad:

```text
$XDG_STATE_HOME/schauwerk/fundus/durability/current.json
```

mit Fallback auf:

```text
~/.local/state/schauwerk/fundus/durability/current.json
```

Für kontrollierte Umgebungen kann `SCHAUWERK_FUNDUS_DURABILITY_EVIDENCE` einen anderen exakten Receipt-Pfad setzen.

Evidence innerhalb des Fundus-Data-Roots wird fail-closed verworfen, weil sich ein Beleg nicht selbst als Bestandteil des attestierten Inventars legitimieren darf.

## Doctor-Semantik

`fundus doctor` unterscheidet drei Zustände:

- **fehlend:** kein Receipt; Core kann gesund sein, aber das aktuelle Inventar besitzt keine Restore-Autorität;
- **gültig aber stale:** Receipt ist intern korrekt, bindet jedoch eine frühere Fundus-Revision;
- **gültig und current:** Receipt, Dateizahl, Gesamtbytes und heutiger Inventar-Digest stimmen exakt überein.

Nur im letzten Fall gilt:

```text
object_store_authoritative=true
restore_verified_current=true
```

Eine einzige neue, entfernte oder geänderte Fundus-Datei macht die Evidenz automatisch stale. Es gibt keine zeitbasierte Schonfrist und keine Ähnlichkeitsheuristik.

Ein vorhandenes, aber formal ungültiges oder manipuliertes Receipt macht den Doctor selbst rot. Ein fehlendes oder lediglich stale Receipt macht dagegen die Durability-Autorität falsch, nicht automatisch den Fundus-Core technisch kaputt.

## Nichtbehauptungen

Durability Evidence v1 ist keine kryptografische Signatur eines externen Providers und keine Provider-Attestierung. Der Eigendigest schützt die interne Receipt-Bindung, nicht gegen einen vollständig kompromittierten lokalen Benutzerkontext.

Ein aktueller Restore-Beleg ersetzt weder Provenienz noch visuelle Acceptance, Package-Verifikation oder Reproducibility. Er beweist ausschließlich, dass die exakt gebundene Fundus-Revision einen vollständigen staged Restore aus einem exakten Backup-Snapshot bestanden hat.

Schauwerk erzeugt dieses Receipt nicht selbst im normalen Asset-Lifecycle und schreibt dafür nicht in fremde Repositories. Der Backup-/Restore-Producer wird unter seiner eigenen Autorität integriert; Grabowski übernimmt die Cross-Repo-Integration.
