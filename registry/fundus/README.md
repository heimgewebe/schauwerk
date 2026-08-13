# Schauwerk Fundus Registry

Diese Registry enthält kleine, Git-versionierte Semantik für wiederverwendbare visuelle Assets und Rezepte. Große Quellbytes liegen ausdrücklich nicht hier, sondern content-addressed unter dem privaten Fundus-State.

- `recipes/`: deterministische Transformationsverträge.
- `assets/`: entsteht erst mit realen, digestgebundenen Quellen.

Ein Asset-Manifest erklärt Herkunft deklarativ; ein `origin`-Feld ist kein kryptografischer Herkunftsbeweis. Schauwerk baut immutable Pakete, besitzt aber keine Cross-Repo-Mutationsautorität. Die Integration in ein Zielrepository bleibt Aufgabe von Grabowski unter einer eigenen Zielrepo-Lane.

V1-Adapterrezepte: `svg-mask-v1`, `raster-png-v1`, das optionale `vtracer-color-v1` und `vtracer-alpha-mask-v1` für transparente Linien-/Ornamentquellen. Vendorentscheidungen sind in `docs/fundus/adapter-benchmark-v1.md` evidenzgebunden.
