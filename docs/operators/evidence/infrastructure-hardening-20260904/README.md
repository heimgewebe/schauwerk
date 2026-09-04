# Schauwerk infrastructure hardening acceptance — 2026-09-04

Diese Evidence bindet die gehärtete Infrastrukturrevision, ohne die historische SW-013-Acceptance vom 11. Juli 2026 umzuschreiben.

## Anlass

Vor einem Einsatz mit Klasse und Lehrer wurden die operativen Grenzen von Schauwerk frisch geprüft. Dabei wurden unter anderem ein nicht vollständig beobachtender Miro-Credential-Statuspfad, bewegliche Action-Tags im Hauptvalidator, offene CodeQL-Sicherheitsmeldungen sowie deaktiviertes GitHub Secret Scanning sichtbar.

## Gebundene Änderungen

- Credential-Lesezugriffe erzeugen oder chmodden keinen State und keine Lockdatei.
- Schreibfehler auf nicht beschreibbarem Credential-State werden als typisierte Credentialfehler behandelt.
- Benutzersichtbare CLI-Ausgabe entfernt Werte sensitiver Schlüssel rekursiv.
- SW-009-Kandidaten unterscheiden echte Miro-Hosts von ähnlich benannten Fremdhosts und akzeptieren in lokalen Pfadfeldern keine URLs.
- Publication-Dateien werden descriptor-relativ mit `O_NOFOLLOW` aus dem bereits geöffneten Bundle gelesen.
- Dynamische HTTP-Headerwerte lehnen Steuerzeichen fail-closed ab.
- Die Actions des Hauptvalidators sind an exakte Commit-SHAs gebunden; ein Regressionstest schützt dieses Pinning.
- Der optionale Chrome-Browser-Smoke prüft zuerst eine unabhängige Headless-Lauffähigkeit in isolierten Temp-/XDG-Pfaden; ein echter Schaubildfehler bleibt danach testwirksam, eine nur installierte aber nicht lauffähige Browser-Runtime wird nicht mit Produktversagen verwechselt.

## Acceptance-Grenze

Das Acceptance-Receipt bindet die exakten Implementierungs- und Testbytes dieser Revision und verweist auf die unveränderte historische SW-013-Acceptance als Parent-Evidence. Es behauptet ausdrücklich nicht:

- dass Miro live autorisiert ist;
- dass GitHub-Repository-Sicherheitseinstellungen bereits umgestellt wurden;
- dass ein produktiver Unterrichtseinsatz stattgefunden hat;
- dass historische SW-013-Bytes nachträglich akzeptiert oder verändert wurden.

Provider-Mutation und produktive Veröffentlichung wurden für diese Acceptance nicht durchgeführt.
