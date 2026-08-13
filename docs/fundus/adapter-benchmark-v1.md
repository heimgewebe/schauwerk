---
id: schauwerk-fundus-adapter-benchmark-v1
role: evidence
status: active
doc_type: architecture-evidence
title: Schauwerk Fundus Adapter Benchmark v1
---

# Schauwerk Fundus Adapter Benchmark v1

## Entscheidung

Fundus verwendet **Pillow 12.2.0** für `raster.png.rgba.v1`. Optionales Raster-zu-Vektor-Tracing verwendet **VTracer 0.6.15** mit `trace.vtracer.color.v1` und explizitem `path_precision=3`. VTracer bleibt im Extra `schauwerk[trace]`; der Core bleibt ohne VTracer importierbar.

VTracer-Ausgabe wird nicht direkt vertraut. Fundus leitet `viewBox` aus den bereits geprüften Quellmaßen ab, entfernt das unnötige Root-Attribut `version` und führt danach unverändert `svg.decorative.v1` aus.

## Reproduktion

```bash
python scripts/fundus_adapter_benchmark.py
```

Der Runner erzeugt deterministische Fixtures und misst Wiederholbarkeit, Pixelgleichheit bzw. Trace-Rückvergleich, Metadatenentfernung, Sanitizer-Fixpunkt, Pfadzahl, Outputgröße und Laufzeit. Laufzeiten sind Hostmesswerte, keine portable Zusage.

### Raster, Heim-PC, 13. August 2026

| Kandidat | deterministisch | pixelgenau | Median | Outputsumme |
|---|---:|---:|---:|---:|
| Pillow 12.2.0 | ja | ja | ca. 7 ms | 35,313 B |
| ImageMagick 6.9.11-60 | ja | ja | ca. 19 ms | 31,480 B |

ImageMagick erzeugte kleinere PNGs. Pillow gewinnt den Core-Vertrag wegen gleicher Korrektheit bei weniger Prozesskomplexität und deutlich niedrigerer gemessener Latenz. Outputgrößenoptimierung bleibt ein separater Packaging-Schritt.

Die lokal vorhandene Pillow-Version 12.3.0 reproduzierte denselben Befund, war am 13. August 2026 im verwendeten Paketindex aber nicht als installierbares Release verfügbar. Pillow 12.2.0 wurde deshalb separat aus einem CPython-3.12-Wheel geprüft und lieferte identische Rasterbytes, Pixelkorrektheit und Adapterentscheidung; CPython-3.11- und CPython-3.12-manylinux-Wheels für 12.2.0 wurden als verfügbar verifiziert.

### Trace, VTracer 0.6.15

| Precision | deterministisch | Fixpunkt | Pfade | SVG | Mean Error |
|---:|---:|---:|---:|---:|---:|
| 3 | ja | ja | 5 | 6,236 B | 2.422993 / 255 |
| 8 | ja | ja | 5 | 9,860 B | 2.422901 / 255 |

Die Qualitätsdifferenz liegt unter `0.01 / 255`; Precision 3 ist rund 36.8 Prozent kleiner. Deshalb wird Precision 3 fest verdrahtet. CPython-3.11- und CPython-3.12-manylinux-Wheels für VTracer 0.6.15 wurden als verfügbar verifiziert; der 3.12-Wheel wurde zusätzlich unter Python 3.12 erfolgreich importiert.

## Sicherheitsgrenze

Rasterquellen werden vor dem Decoder vom Fundus-Media-Inspector geprüft und durch Pixel-/Outputbudgets begrenzt. Pillow muss zur Laufzeit exakt 12.2.0 entsprechen; eine abweichende bereits vorhandene Umgebung wird als nicht verfügbar markiert, `doctor.ok=false`, und Rastertransformationen werden fail-closed abgewiesen. Mehrbild-Raster und nicht normalisierte EXIF-Orientierung werden fail-closed abgewiesen. Trace normalisiert die Rasterquelle zuerst über denselben Pillow-Vertrag und hat zusätzlich strengere Dimensions-, Pixel- und SVG-Bytebudgets. VTracer muss exakt Version 0.6.15 entsprechen. Jedes erzeugte SVG muss den bestehenden `svg.decorative.v1`-Sanitizer passieren; dessen Regeln für aktive Inhalte, externe Ressourcen, XML, Elemente und Pfade bleiben unverändert autoritativ.

Potrace, rembg und Inkscape bleiben unselektiert: Im aktuellen Liveinventar waren sie nicht installiert und ein reproduzierbarer Fundus-Nutzenbeweis fehlt.
