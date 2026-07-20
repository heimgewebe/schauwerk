# Operator-Ökosystem auf heim-pc

Stand: 19. Juli 2026, 17:31:58 CEST

## Zweck

Dieses Schauwerk zeigt den lokalen Operator-Kontrollkreis auf `heim-pc`. Es konzentriert sich auf Autorität, Koordination, Ausführung, technische Wahrheiten, Beobachtung, Darstellung und Sicherheitsgrenzen. Produktprojekte werden bewusst als eigene fachliche Domäne zusammengefasst, damit die Steuerungslogik lesbar bleibt.

Die Darstellung ist eine eingefrorene, quellgebundene Projektion. Sie ist weder ein Ersatz für Systemkatalog, Bureau, GitHub, systemd noch für direkte Provider-Readbacks.

## Quellenbindung

- Schauwerk-Basis: `origin/main` bei `5ef44d5`.
- Aktiver Systemkatalog-Release: `041bfe52ae5bb02636f17adc70ffbf45656d166b`.
- Systemkatalog-Inventar `registry/ecosystem/nodes.json`: SHA-256 `418b6d6c433fc7c1fb6b7fe69a9c4676011ec60ba589512762ab7f2649737848`.
- Aktiver Leitstand-Release: `1484a584af057707c22667959785330482aa1f4c`; Dienstzustand `active/running`, Ergebnis `success`, Neustarts `0`.
- Grabowski-Runtime: Release `60d2bf1582b3-srcsetc717833fb75c-locke6664d600b6c-contract2c47105e3c8e`; Deployment vollständig und Integrität gültig.
- Grabowski-Audit: Kette gültig, beschreibbar, kein Rotationsbedarf; letzter aktiver Record-Digest `730fb6210075516f6fdeacdd89962dcffa0f67d567e056272a5b9dd30c3b36a4`.
- Ressourcenkoordination: 135 aktive Leases im Snapshot.
- Laufzeitbeobachtung: `grabowski-operator.service`, `leitstand.service`, `repoground.service` und `tunnel-client-grabowski.service` waren aktiv.
- Direkter Task-Readback: Zwei Grabowski-Tasks liefen – ein vollständiger RepoGround-Validierungslauf und eine Bureau-Wahrheitsmodell-Prüfung.

## Wesentlicher Befund

Die zuerst gelesene kompakte Task-Projektion meldete `running=0`. Ein direkter systemd-Readback zeigte dagegen zwei aktive Grabowski-Task-Units; die anschließenden Einzel-Readbacks bestätigten beide als `running`.

Daraus folgt:

1. Verdichtete Projektionen sind Orientierung, nicht Primärwahrheit.
2. Vor Wirkung, Merge, Deployment oder Abschluss ist ein direkter Readback erforderlich.
3. Leitstand und Schauwerk müssen Aktualität und Herkunft sichtbar machen, statt einen scheinbar einheitlichen Zustand zu behaupten.

## Leselogik

1. **Alexander** setzt Ziel, Grenzen und Abbruchautorität.
2. **ChatGPT Operator** übersetzt den Auftrag in prüfbare Arbeit.
3. **Bureau** hält Aufgaben- und Abschlusswahrheit; **Systemkatalog** hält Rollen und stabile Beziehungen.
4. **Grabowski** führt über isolierte Workspaces, Leases und typisierte Werkzeuge aus.
5. Änderungen durchlaufen **Repositories**, **GitHub/CI** und **Prüfgates**, bevor sie auf Laufzeiten wirken.
6. **Primärbeobachtung**, **Chronik**, **RepoGround** und **Auditkette** liefern unterschiedliche Evidenzachsen.
7. **Leitstand** verdichtet Zustand; **Schauwerk** erzeugt nachvollziehbare visuelle Projektionen und liefert sie kontrolliert an Miro und den Companion.
8. **Kill-Switch, Blockaden, Power Broker und Recovery** begrenzen Wirkung und ermöglichen sichere Fortsetzung.

## Grenzen

- Die Karte behauptet keine Vollständigkeit aller Dienste, Repositories oder Geräte auf `heim-pc`.
- Die Zahl aktiver Tasks und Leases ist zeitgebunden und kann unmittelbar nach dem Snapshot abweichen.
- Der Provider-Readback beweist die Umsetzung des Darstellungspakets, nicht automatisch ästhetische Qualität.
- Miro und der öffentliche Companion sind Oberflächen. Kanonische Wahrheiten bleiben in ihren jeweiligen Quellsystemen.

## Live-Auslieferung

Die Darstellung wurde auf einem neuen, ausschließlich dafür erzeugten Miro-Board mit dem Alias `operator-ecosystem-heim-pc-20260719` ausgeliefert. Das geprüfte Paket ist gebunden an:

- Eingabe-Digest `2582c19e4cfd4aa6c7972c3ed1fa69de6f91fa22e0785e69d1d0040dcb01e2e4`;
- Paket-Digest `ea19c156863b3c6365c4c12848366ff9e5bec3f654ff61378fb19d0d0365e98e`;
- Preview-Digest `cceb0328312505f6acc78a3420507c85b2ea3e219cfe7a4e942fd8e63172aa6a`;
- Miro-Referenzdigest `eaa087839f2fff2c`.

Der Native-Executor verifizierte beide Operationen einzeln:

1. Die Layout-Operation erstellte 39 Objekte ohne fehlgeschlagene oder übersprungene Elemente.
2. Das Mermaid-Quellwidget stimmt in Inhalt, Sprache, Position und Zeilennummerndarstellung mit dem Paket überein.

Der unabhängige Snapshot ist wiederholbar und enthält 34 über `board_list_items` sichtbare Objekte: sechs Frames, zwölf Texte, dreizehn Formen, ein Dokument, eine Tabelle und ein Code-Widget. Geometrieabdeckung beträgt 100 Prozent; es gibt keine Überlappung und keine Lesbarkeitswarnung. Ein getrennter `layout_read`-Readback bestätigt zusätzlich sechs Connectoren.

### Beobachtungsgrenze

`board_list_items` und der darauf aufbauende Qualitätslauf geben Connectoren nicht zurück. Deshalb meldete der äußere Delivery-Abschluss fälschlich 34 statt 40 erzeugte Objekte sowie `failed` und `partial_mutation`; der Qualitätslauf setzte den nicht beobachtbaren Connectorwert fälschlich auf null. Das ist kein fehlgeschlagenes Board: Layout und Mermaid-Operation sind vollständig verifiziert, Snapshot und Layout-Readback ergänzen sich widerspruchsfrei.

Der nachhaltige Fix ist als Bureau-Task `OPERATOR-ECOSYSTEM-REDUNDANCY-V1-T039` registriert; die Registrierung wurde in Bureau-PR #728 veröffentlicht. Der Task verlangt getrennte Zählungen für Providererzeugung, allgemeines Inventar und Connectoren sowie negative Tests, damit echte Connectorverluste weiterhin fail-closed bleiben.

Der Web-SDK-Companion bleibt eine getrennte Achse. Seine Developer-App-, Teaminstallations-, Hosting- und In-Board-OAuth-Gates werden durch diese native Board-Auslieferung nicht behauptet.

## Erzeugung

```text
schauwerk visual route docs/operators/fixtures/operator-ecosystem-heim-pc-v1.json
schauwerk visual package-check <representation-package>
schauwerk visual preview <representation-package>
schauwerk visual deliver <board-alias> <representation-package>
```

## Visuelle Korrektur vom 20. Juli 2026

Authentifizierte Aufnahmen des ausgelieferten Boards widerlegten die frühere ästhetische
Einordnung. Der damalige Wert `100` belegte ausschließlich die maschinenlesbare Struktur:
Objektzahlen, deklarierte Geometrie, Snapshot-Wiederholbarkeit und Connector-Evidenz. Er
belegte nicht das tatsächliche Browser-Rendering.

Die Aufnahmen zeigten vier konkrete Fehler:

1. Mermaid wurde als Quelltext-Widget abgelegt, nicht als Diagramm gerendert.
2. Miro positionierte lange Connector-Beschriftungen über benachbarten Knoten.
3. Das automatisch dimensionierte Dokument im Beleg-Frame wuchs zu einer großen weißen
   Fläche.
4. Die automatisch dimensionierte Tabelle im Entscheidungs-Frame war in der Übersicht kaum
   lesbar.

Die nachhaltige Korrektur ist unter
`OPERATOR-ECOSYSTEM-REDUNDANCY-V1-T042` gebunden. Die ursprünglich vorgesehene T040 war
bereits kanonisch durch eine unabhängige HausKI-Aufgabe belegt und durfte nicht überschrieben
werden. Die Korrektur ändert den Vertrag wie folgt:

- Die ergänzende Mermaid-Repräsentation bleibt als quellgebundenes Artefakt erhalten. Auf
  dem Miro-Board wird aus demselben semantischen Modell über `diagram_create` ein natives
  Flussdiagramm erzeugt; ein Quelltext-Widget gilt nie wieder als gerenderte Darstellung.
- Kompakte kontrollierte Frames enthalten keine providerseitig frei dimensionierten
  Dokumente oder Tabellen. Beleg und Darstellungsentscheidung verwenden begrenzte Formen.
- Semantische Beziehungen bleiben Connectoren; ausführliche Beziehungstexte liegen in einer
  geometrisch begrenzten Legende. Ein statischer Risikocheck blockiert unzureichenden Abstand
  für providerpositionierte Connector-Texte.
- Jede neue Live-Lieferung trägt zunächst den Status
  `pending_authenticated_provider_capture`. Eine visuelle Freigabe ist nur mit einer
  authentifizierten Aufnahme des exakten Nachher-Zustands zulässig.
- API- und DSL-Readbacks bleiben notwendige Konformitätsbelege, dürfen aber nicht mehr als
  ästhetische Abnahme bezeichnet werden.

Die Korrektur wird auf demselben allowlistgebundenen Board durchgeführt. Ein zweites Board
oder eine parallele Kopie ist nicht Teil des Vertrags.
