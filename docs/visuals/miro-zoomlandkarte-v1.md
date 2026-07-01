# Miro Zoomlandkarte v1

Status: active

## Zweck

Die Zoomlandkarte ist ein Miro-Template fuer groessere Lernstoffmengen. Sie uebernimmt das Prinzip der Nicole-Musiktherapie-Vorlage: Im Zoom-out sind nur Cluster, Prioritaeten und Arbeitsstrecke sichtbar. Im Zoom-in erscheinen die Inhalte innerhalb der Cluster.

## Layout-Prinzip

- `00 Gesamtueberblick`: Thema, Leitidee, Cluster-Legende
- `01 Produktionsstrecke`: Sichten -> Sortieren -> Clustern -> Vertiefen -> Erklaeren -> Sichern
- `02 Legende Risiko`: Prioritaet und Schutzgrenzen
- `A`-Cluster: Orientierung, Ziele, Begriffe
- `B`-Cluster: Lernweg und Transfer
- `C`-Cluster: Luecken, Risiken, Quellen und Material

## CLI

```text
schauwerk miro learn render <input.yml> --template zoomlandkarte --json
schauwerk miro learn apply <alias> <input.yml> --template zoomlandkarte --json
schauwerk miro learn live-test <input.yml> --template zoomlandkarte --json
```

Ohne `--template zoomlandkarte` bleibt der klassische Learning-Renderer aktiv.

## Grenzen

Die Zoomlandkarte ist fuer Stofflandschaften gedacht, nicht fuer sehr kurze Einzelimpulse. Bei kleinen Themen kann der klassische Renderer uebersichtlicher sein.
