---
id: schauwerk-fundus-adapter-benchmark-v1
role: evidence
status: active
doc_type: architecture-evidence
title: Schauwerk Fundus Adapter Benchmark v1
---

# Schauwerk Fundus Adapter Benchmark v1

## Entscheidung

Fundus verwendet **Pillow 12.2.0** für `raster.png.rgba.v1`. Optionales Raster-zu-Vektor-Tracing verwendet **VTracer 0.6.15** mit `trace.vtracer.color.v1` und explizitem `path_precision=3`. VTracer bleibt im Extra `schauwerk[trace]`; der Core bleibt ohne VTracer importierbar. Transparente Construction-Master mit primär alpha-getriebener Linieninformation verwenden zusätzlich `trace.vtracer.alpha-mask.v1`; ein realer transparenter Construction-Master-Proof etablierte Alpha≥8 als kleinste robuste Schwelle, bevor ungeeignetes Farbtracing wegen übergroßer Roh-SVGs fail-closed abgewiesen wurde.

VTracer-Ausgabe wird nicht direkt vertraut. Fundus leitet `viewBox` aus den bereits geprüften Quellmaßen ab, entfernt das unnötige Root-Attribut `version` und führt danach den vorgesehenen SVG-Sanitizer aus. Evidenzwerkzeuge lesen die aktuelle Trace-Konfiguration über die öffentliche read-only Funktion `trace_profile_contract()` und verwenden `normalize_vtracer_svg()` für dieselbe Normalisierungsgrenze wie das produktive Tracing; der Benchmark importiert keine privaten Settings mehr.

## Reproduktion

```bash
PYTHONPATH=src .venv/bin/python scripts/fundus_adapter_benchmark.py
```

Der Runner erzeugt einen deterministischen semantischen Fixture-Korpus und misst Wiederholbarkeit, Pixelgleichheit bzw. Trace-Rückvergleich, Metadatenentfernung, Sanitizer-Fixpunkt, Pfadzahl, Outputgröße und Laufzeit. Laufzeiten sind Hostmesswerte, keine portable Zusage. Jeder semantische Fixture-Eintrag erhält zusätzlich einen kanonischen PNG-SHA-256-Digest, damit spätere Benchmarkläufe nicht stillschweigend gegen andere Testbilder entscheiden.

## Fixture-Korpus, 14. August 2026

### Raster

Der Raster-Korpus deckt drei unterschiedliche Fehlerklassen ab:

- `gradient_alpha`: Farbverläufe, harte Formen und partielle Transparenz;
- `fine_line_alpha`: feine Linien auf transparentem Grund;
- `deterministic_texture`: dichtes deterministisches Material-/Detailmuster.

Jeder semantische Fixture wird als PNG und JPEG sowie bei verfügbarer Pillow-WebP-Unterstützung als WebP geprüft. Auf dem Heim-PC ergibt das neun kodierte Rasterfälle.

| Kandidat | deterministisch | pixelgenau | Median über Korpus | Outputsumme |
|---|---:|---:|---:|---:|
| Pillow 12.2.0 | ja | ja | 12.413 ms | 576,516 B |
| ImageMagick 6.9.11-60 | ja | ja | 14.045 ms | 422,959 B |

Beide Kandidaten entfernten die Testmetadaten und waren über alle kodierten Fixtures pixelgenau. ImageMagick erzeugt weiterhin kleinere PNG-Outputs. Pillow bleibt der Core-Adapter, weil die Korrektheit gleich ist, der gemessene Gesamtmedian leicht niedriger liegt und keine zusätzliche Prozess-/Binary-Grenze in den Fundus-Core eingeführt wird. Outputgrößenoptimierung bleibt ein separater Packaging-Schritt.

### Trace

Der Trace-Korpus besteht aus:

- `flat_shapes`: wenige große Farbflächen und klare Konturen;
- `fine_lines`: zahlreiche dünne Bögen und Kreuzlinien;
- `nested_contours`: verschachtelte Konturen, Rundungen und überlagerte Flächen.

Die Precision-Entscheidung gilt nur, wenn **jeder** Fixture bei Precision 3 und 8 denselben Pfadcount, einen Sanitizer-Fixpunkt, denselben maximalen Kanalfehler und höchstens `0.01 / 255` Differenz im mittleren Roundtrip-Fehler zeigt.

| Precision | deterministisch | Fixpunkt | Pfade gesamt | SVG gesamt | Median |
|---:|---:|---:|---:|---:|---:|
| 3 | ja | ja | 133 | 105,003 B | 20.101 ms |
| 8 | ja | ja | 133 | 157,204 B | 20.915 ms |

Roundtrip-Mittelwerte pro Fixture:

| Fixture | Precision 3 | Precision 8 | Delta |
|---|---:|---:|---:|
| `flat_shapes` | 2.422993 | 2.422901 | 0.000092 |
| `fine_lines` | 15.843307 | 15.843281 | 0.000026 |
| `nested_contours` | 7.697460 | 7.697556 | 0.000096 |

Damit bleibt der Korpus qualitativ äquivalent. Precision 3 ist über den gesamten Korpus rund **33,2 Prozent kleiner** und minimal schneller; `path_precision=3` bleibt deshalb die evidenzgestützte Vorgabe.

## Historische Ausgangsmessung, 13. August 2026

Die ursprüngliche Einzel-Szene hatte bereits Pillow gegenüber ImageMagick sowie VTracer Precision 3 gegenüber 8 verglichen. Sie war ausreichend für die erste Adapterauswahl, aber zu schmal als dauerhafte Regressionsbasis. Der Korpus vom 14. August ersetzt diese Einzel-Szene als aktuelle Entscheidungsgrundlage; die frühere Messung bleibt nur historische Evidenz.

Die separat geprüften CPython-3.11- und CPython-3.12-manylinux-Wheels für Pillow 12.2.0 und VTracer 0.6.15 bleiben Teil der ursprünglichen Portabilitätsevidenz.

## Sicherheitsgrenze

Rasterquellen werden vor dem Decoder vom Fundus-Media-Inspector geprüft und durch Pixel-/Outputbudgets begrenzt. Pillow muss zur Laufzeit exakt 12.2.0 entsprechen; eine abweichende bereits vorhandene Umgebung wird als nicht verfügbar markiert, `doctor.ok=false`, und Rastertransformationen werden fail-closed abgewiesen. Mehrbild-Raster und nicht normalisierte EXIF-Orientierung werden fail-closed abgewiesen. Trace normalisiert die Rasterquelle zuerst über denselben Pillow-Vertrag und hat zusätzlich strengere Dimensions-, Pixel- und SVG-Bytebudgets. VTracer muss exakt Version 0.6.15 entsprechen. Jedes erzeugte SVG muss den für sein Profil vorgesehenen Sanitizer passieren; dessen Regeln für aktive Inhalte, externe Ressourcen, XML, Elemente und Pfade bleiben unverändert autoritativ.

Potrace, rembg und Inkscape bleiben unselektiert: Ein reproduzierbarer Fundus-Nutzenbeweis für einen zusätzlichen Adapter fehlt weiterhin.
