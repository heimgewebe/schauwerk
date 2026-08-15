# Schauwerk Fundus Registry

Diese Registry enthält kleine, Git-versionierte Semantik für wiederverwendbare visuelle Assets und Rezepte. Große Quellbytes liegen ausdrücklich nicht hier, sondern content-addressed unter dem privaten Fundus-State.

- `briefs/`: versionierte Image Briefs für generierte oder generativ bearbeitete Source-Master; die maschinelle Bindung erfolgt über den beim `fundus brief` vorbereiteten Digest.
- `families/`: semantische Asset-Familien.
- `recipes/`: deterministische Transformationsverträge.
- `assets/`: entsteht erst mit realen, digestgebundenen Quellen.

Ein Asset-Manifest erklärt Herkunft deklarativ; ein `origin`-Feld ist kein kryptografischer Herkunftsbeweis. Ein Source-Master ist noch kein freigegebenes Produktionsasset. Schauwerk baut erst nach technischer Prüfung und visueller Acceptance immutable Pakete, besitzt aber keine Cross-Repo-Mutationsautorität. Die Integration in ein Zielrepository bleibt Aufgabe von Grabowski unter einer eigenen Zielrepo-Lane.

V1-Adapterrezepte: `svg-mask-v1`, `raster-png-v1`, das optionale `vtracer-color-v1` und `vtracer-alpha-mask-v1` für transparente Linien-/Ornamentquellen. Vendorentscheidungen sind in `docs/fundus/adapter-benchmark-v1.md` evidenzgebunden.
