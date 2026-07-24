---
doc_type: operator-contract
status: active
title: Python runtime thread stack v1
---

# Python runtime thread stack v1

## Zweck

Dieser Vertrag diagnostiziert einen lokalen Linux-ELF-Laufzeitfehler, bei dem Python beim Erzeugen eines Worker-Threads generisch `RuntimeError: can't start new thread` meldet, obwohl Prozess-, Speicher- und cgroup-Grenzen ausreichend sind.

Schauwerk behandelt die Fehlermeldung nicht als Beweis für Ressourcenmangel. Erst Systemaufruf- und ELF-Evidenz darf die Ursache bestimmen.

## Festgestellte Ursache vom 24. Juli 2026

Die auf dem heim-pc installierten uv-Builds CPython 3.12.11 und 3.12.12 besaßen keinen `PT_GNU_STACK`-Program-Header. Der dynamische Loader versuchte deshalb beim Anlegen eines neuen Thread-Stacks, diesen mit `PROT_READ|PROT_WRITE|PROT_EXEC` zu schützen. Die aktive W^X-Härtung verweigerte das korrekt mit `EPERM`; Python reduzierte diesen konkreten Fehler anschließend auf `can't start new thread`.

Nicht ursächlich waren:

- `RLIMIT_NPROC`;
- der cgroup-PID-Rahmen;
- verfügbarer Arbeitsspeicher;
- das Schauwerk-Virtualenv;
- Miro oder der REST-Provider.

## Reparaturmodell

Die Host-Härtung bleibt unverändert. Der Interpreter erhält stattdessen einen expliziten `PT_GNU_STACK`-Header mit ausschließlich `PF_R|PF_W`.

Der Schauwerk-Pfad akzeptiert nur:

- ELF64, Little Endian, x86_64;
- `ET_EXEC` oder `ET_DYN`;
- genau eine gebundene reguläre, owner-owned und einzeln verlinkte Quelldatei;
- keinen vorhandenen `PT_GNU_STACK`;
- genau einen streng geformten GNU/Linux-ABI-`PT_NOTE`-Header mit `GNU`-Name, `NT_GNU_ABI_TAG` und Linux-OS-ID als ersetzbaren Program-Header-Slot.

Die Reparatur ist **output-only**:

1. Die Quelldatei wird descriptor- und Metadaten-gebunden gelesen.
2. Der passende `PT_NOTE`-Eintrag wird im Speicher zu `PT_GNU_STACK` mit Flags `RW` umgewandelt.
3. Der Zielordner muss dem Nutzer gehören und darf nicht gruppen- oder weltbeschreibbar sein.
4. Eine neue Ausgabedatei wird mit `O_EXCL` erzeugt; ihre Rechte werden descriptorgebunden gesetzt.
5. Größe, Eigentum, Linkanzahl, Modus, Pfad-Inode und Bytes werden am weiterhin offenen Deskriptor zurückgelesen.
6. Der Quellpfad wird niemals automatisch ersetzt.

Ein In-place-Patch, Root-Zugriff, ein ausführbarer Stack oder eine Lockerung von W^X gehören ausdrücklich nicht zum Vertrag.

## CLI

Aktuellen Basisinterpreter oder einen expliziten Python-ELF-Pfad nur prüfen:

```text
schauwerk runtime python-thread-stack inspect [PYTHON-EXECUTABLE] --json
```

Eine create-only Reparaturausgabe erzeugen:

```text
schauwerk runtime python-thread-stack repair PYTHON-EXECUTABLE \
  --output PYTHON-EXECUTABLE.repaired --json
```

Die CLI ersetzt die aktive Runtime absichtlich nicht. Ein Operator muss Digest, ELF-Readback, Threadstart und betroffene Virtualenvs separat verifizieren, bevor ein atomarer Austausch erwogen wird.

## Live-Nachweis T002

Die lokale CPython-3.12.12-Datei wurde nach einer vorherigen Kandidatenprüfung digestgebunden atomar ersetzt:

- Original-SHA-256: `52f97dd7591d651870416792ec5d9b8fe656669fe726a9fed4ec3140ecba8ae4`
- Reparatur-SHA-256: `e082b57e5bd1f4604480fca642cc276ae59b669a0d7b9c87e6b4b5cbf3544ac2`
- vorher: kein `PT_GNU_STACK`, Thread-Stack-`mprotect(RWX)` endet mit `EPERM`
- nachher: `PT_GNU_STACK RW`, Thread-Stack-`mprotect(RW)` erfolgreich, `clone3` erfolgreich

Danach bestanden:

- direkter CPython-3.12.12-Threadstart;
- Threadstart aus dem bestehenden Schauwerk-Virtualenv;
- der normale Projektpfad `uv run schauwerk miro rest doctor --require-write --json` mit unveränderter Live-Autorisierungsprüfung und den Scopes `boards:read` und `boards:write`.

Der create-only Schauwerk-Pfad erzeugte aus dem unveränderten Originalbackup bytegenau denselben Reparatur-Digest wie die aktive Runtime.

Der sanitierte Nachweis liegt unter `docs/operators/evidence/python312-thread-stack-repair-20260724.json`.

## Betriebsgrenzen

Ein späteres `uv python install`, eine Runtime-Aktualisierung oder ein Neuaufbau kann das Provider-Binary ersetzen. Deshalb gilt nach jedem Interpreterwechsel erneut:

1. `python-thread-stack inspect` ausführen;
2. einen echten Threadstart prüfen;
3. betroffene Netzwerkpfade erst danach verwenden.

Der Nachweis garantiert weder zukünftige Binary-Identität noch, dass alle geladenen Erweiterungsmodule einen nicht ausführbaren Stack deklarieren.
