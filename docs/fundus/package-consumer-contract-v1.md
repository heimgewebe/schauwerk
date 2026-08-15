---
id: schauwerk-fundus-package-consumer-contract-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Package Consumer Contract v1
summary: Runtime-independent verification and portable consumer locking for immutable Fundus packages.
---

# Schauwerk Fundus Package Consumer Contract v1

## Zweck

Ein akzeptiertes Fundus-Package soll nach der Integration ohne laufende Schauwerk-Installation überprüfbar und konsumierbar bleiben. Deshalb trennt der Consumer-Vertrag drei Dinge strikt:

1. das bereits immutable Fundus-Package;
2. eine read-only Package-Verifikation;
3. ein separates immutable `schauwerk-fundus-consumer-lock.v1`-Metadatum.

Schauwerk verändert dabei weder das Package nachträglich noch ein fremdes Consumer-Repository. Die Integration von Package und Lock bleibt Aufgabe von Grabowski unter der Autorität des Zielrepos.

## Package-Verifikation

`schauwerk fundus package-verify PACKAGE_DIR --json` prüft ein Package ohne Registry-, Build- oder Acceptance-Store-Zugriff.

Geprüft werden:

- Package-Schema v1 oder v2;
- UTF-8-JSON ohne doppelte Schlüssel, `NaN` oder Infinity;
- exakt die kanonische Fundus-JSON-Serialisierung von `fundus-package.json`;
- `package_digest` gegen den kanonischen Manifestinhalt;
- `consumer_runtime_dependency=false`;
- kanonische und eindeutige relative Assetpfade;
- exakter Dateisatz ohne zusätzliche oder fehlende Dateien;
- sichere Verzeichnis- und Dateimetadaten ohne Symlinks oder Hardlinks;
- deklarierte Dateigröße und SHA-256 jeder Produktionsdatei;
- deklarierter MIME-/Medientyp gegen die tatsächlichen Bytes;
- für SVG je nach Outputrolle das passive `svg.mask.v1`- oder `svg.decorative.v1`-Profil, einschließlich Verbot aktiver und externer Ressourcen;
- exakte `SHA256SUMS`-Bytes einschließlich des Digests von `fundus-package.json`.

Der Package-Root bleibt während der Prüfung über einen No-Follow-Deskriptor gepinnt. Inventar und sämtliche Dateien werden descriptor-relativ geprüft; ein zweiter vollständiger Verifikationspass und ein Root-Identity-Postflight blockieren Additions-, Removal-, Replacement- und Root-Swap-Rennen. `ok=true` beschreibt damit den stabil bestätigten Package-Verzeichniszustand des Returns.

Die Verifikation liest ausschließlich das übergebene Package-Verzeichnis. Sie repariert oder normalisiert keine Consumer-Dateien.

## Consumer Lock

`schauwerk fundus consumer-lock PACKAGE_DIR --data-root ... --json` verifiziert zuerst das Package und erzeugt anschließend ein separates create-or-verify-Metadatum unter dem Fundus-State:

```text
consumer-locks/<asset-id>/<package-digest>/<lock-digest>.json
```

Der Lock enthält ausschließlich Consumer-relevante Bindungen:

- Asset-ID;
- Package-Schemaversion;
- Package-, Build- und Acceptance-Digest;
- SHA-256 des exakten Package-Manifests;
- pro Produktionsdatei Pfad, Rolle, optional Quellrolle, MIME, SHA-256 und Bytezahl;
- `consumer_runtime_dependency=false`;
- eigenen `lock_digest`.

Der Lock ist keine neue visuelle Acceptance und keine neue Package-Revision. Er bindet nur die bereits akzeptierten Produktionsbytes für einen späteren Consumer. Auch beim späteren Einlesen muss seine JSON-Darstellung kanonisch sein und doppelte Schlüssel werden fail-closed abgewiesen.

## Portable Consumer-Prüfung

Nach dem Vendoring kann ein Consumer Package und Lock gemeinsam prüfen:

```bash
schauwerk fundus consumer-check fundus-consumer-lock.json path/to/package --json
```

Diese Prüfung benötigt keine Fundus-Registry, keinen Source-Store, keinen Build-Store und keine Acceptance-Datenbank. Sie verifiziert das Package vollständig erneut und verlangt anschließend exakte Übereinstimmung aller Lock-Bindungen.

Ein Consumer kann dieselbe Semantik auch außerhalb einer laufenden Schauwerk-Installation nachimplementieren: Package- und Lock-Formate sind JSON-Schemas, alle Identitäten sind SHA-256-gebunden und die Produktionsbytes liegen vollständig im Package.

## Architekturgrenze

Der Lock ist bewusst **nicht** Bestandteil des zuvor erzeugten immutable Packages. Ein nachträgliches Hineinschreiben würde dessen Package-Digest verändern und die bestehende Acceptance-Bindung entwerten. Deshalb wird die Materialisierung auch dann fail-closed abgewiesen, wenn ein fehlkonfigurierter `data-root` den berechneten Lock-Pfad innerhalb des Package-Verzeichnisses platzieren würde.

Ebenso schreibt Schauwerk den Lock nicht direkt in Websites, Präsentationen, Miro-Boards oder andere Repositories. Grabowski übernimmt später unter Zielrepo-Autorität beispielsweise:

```text
accepted Fundus package + consumer lock
                 ↓
      target-repo preflight / leases
                 ↓
              vendor
                 ↓
       tests + visual readback
                 ↓
             integration
```

## Nicht-Ziele

Der Consumer Lock ist kein Dependency-Manager, kein CDN-Manifest, kein Updatekanal und keine automatische Freigabe. Er ist außerdem keine kryptographische Signatur, keine Generator- oder Provider-Attestierung, keine Reviewer-Authentifizierung und kein selbständiger Provenienznachweis. Er beweist die interne Integrität und exakte Bindung der ihm zugrunde gelegten Bytes; die Herkunfts- und Acceptance-Autorität bleibt in der Fundus-Lifecycle-Kette. Er entscheidet nicht, ob ein neueres Asset gestalterisch besser ist, und er autorisiert keine Cross-Repo-Mutation.
