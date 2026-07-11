# SW-013 Schaufenster acceptance evidence

Diese Evidence belegt den lokalen, providerneutralen Publikationsvertrag. Sie ist **keine produktive Veröffentlichung**.

## Eingabe

- öffentliches SW-012-Technikpaket aus `../sw012-buehne-20260711/technical/public/`;
- eine eigenständige, digestgebundene Publikationsdeklaration;
- ausschließlich explizit benannte öffentliche Quelle, Dateien und Metadatenfelder.

## Belegte Zustände

- deterministische Preview;
- unveränderliches Objektmanifest mit SHA-256 je Datei;
- aktiver stabiler Link;
- aus Zeitbezug abgeleiteter Ablaufstatus ohne Mutation;
- kontrollierte Rücknahme des Links bei erhaltenem Objekt;
- Release- und Withdrawal-Receipts;
- gemeinsames Acceptance-Receipt mit Hashbindung aller Evidence-Dateien;
- SHA-256-Bindung der geprüften Implementierungs-, Schema-, CLI-, Test- und Vertragsdateien.

## Grenzen

- kein Internet-Upload;
- kein DNS, Hosting, CDN oder Deployment;
- keine Miro-Mutation;
- kein Eingriff in das SW-012-Quellpaket;
- Teststore wurde nur temporär unter `/tmp` erzeugt und nach der Abnahme gelöscht;
- `registry/publications.yaml` bleibt auf `draft`.

## Dateien

- `declaration.json`
- `preview.json`
- `object-manifest.json`
- `active-link.json`
- `release-receipt.json`
- `active-status.json`
- `expired-status.json`
- `withdrawn-link.json`
- `withdrawal-receipt.json`
- `withdrawn-status.json`
- `acceptance-receipt.json`
