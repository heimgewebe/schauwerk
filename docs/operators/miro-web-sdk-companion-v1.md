# Miro Web SDK Companion v1

Stand: 17. Juli 2026

## Zweck

Der Companion ergänzt die receipt-gebundene MCP-Laufzeit um eine interaktive, im Miro-Board eingebettete Lesefläche. Er ersetzt weder den MCP-Executor noch die Miro REST API.

Die statische Anwendung zeigt:

- den redigierten Ausführungs- und Qualitätsstand;
- aktuellen Boardkontext;
- die laufende Boardauswahl;
- einen Fokusgriff auf ausgewählte Objekte;
- einen deterministischen Präsentationsweg durch Frames;
- einen Standalone-Fallback, wenn das Miro Web SDK nicht verfügbar ist.

## Bau

```text
schauwerk miro companion build \
  docs/operators/fixtures/miro-web-sdk-companion-v1.json \
  --output-dir /tmp/schauwerk-miro-companion

schauwerk miro companion check /tmp/schauwerk-miro-companion --json
```

Der Builder akzeptiert ausschließlich das Schema `schauwerk-miro-web-sdk-companion.v1`. Ein vorhandenes oder symlinkgebundenes Ziel wird abgewiesen. Das Ergebnis enthält:

- `index.html` als Miro-App-Einstieg;
- `panel.html` als Boardpanel;
- lokale Anwendungs-JavaScript- und CSS-Dateien;
- das offizielle Miro Web SDK zur Laufzeit ausschließlich von `https://miro.com/app/static/sdk/v2/miro.js`;
- eine normalisierte `config.json`;
- statische Security-Header;
- einen SHA-256-gebundenen `build-receipt.json`.

## Releasevertrag

Der Releasevertrag bindet die verifizierten Bundlebytes an eine öffentliche HTTPS-App-URL und ein nicht vertrauliches Developer-App-Label:

```text
schauwerk miro companion release-create \
  /tmp/schauwerk-miro-companion \
  --app-url https://companion.example.org/ \
  --developer-app-label "Schauwerk Companion" \
  --output /tmp/schauwerk-companion-release.json \
  --json

schauwerk miro companion release-check \
  /tmp/schauwerk-companion-release.json \
  --bundle-dir /tmp/schauwerk-miro-companion \
  --json

schauwerk miro companion release-doctor \
  /tmp/schauwerk-companion-release.json \
  --json
```

Der HTTPS-Doctor prüft fail-closed:

- exakte URL ohne Redirect;
- Status `200`;
- exakte Assetdigests;
- passende Content-Types;
- CSP einschließlich Miro-SDK-Ursprung und `frame-ancestors`;
- Permissions-, Referrer- und `nosniff`-Header.

Der Releasebeleg enthält keine Tokens, Team-IDs oder Board-IDs. GitHub Pages ist für diesen Vertrag kein geeigneter Standardpfad, weil die benötigten benutzerdefinierten Sicherheits- und Einbettungsheader dort nicht verlässlich als Response-Header durchgesetzt werden können.

### Kontrollierter GitHub-Pages-Fallback

Für eine kostenlose, dauerhafte Funktionsprüfung kann der Workflow `companion-pages.yml` den kanonischen Companion aus `main` neu bauen und als GitHub-Pages-Artefakt veröffentlichen. Er verwendet SHA-fixierte Actions, minimale Repository- und Pages-Berechtigungen und entfernt die hostspezifische Datei `_headers`, statt ihre Wirkung vorzutäuschen.

Dieser Pfad belegt nur eine reproduzierbare öffentliche HTTPS-App-URL. Er erfüllt den vollständigen Releasevertrag ausdrücklich nicht, solange CSP, `frame-ancestors`, Permissions-, Referrer- und `nosniff`-Header nicht als echte HTTP-Response-Header nachgewiesen sind. Der Pages-Host darf daher für Miro-Installation und In-Board-Readback verwendet werden, aber nicht als `release-doctor`-PASS oder als gleichwertiger Ersatz für einen headerfähigen Host verbucht werden.

## Headerfähiger Loopback-Host

Der Repository-Host prüft das vollständige Bundle und bindet sich ausschließlich an eine Loopback-Adresse. Er liefert nur die acht öffentlichen Dateien aus dem verifizierten `build-receipt.json`; `_headers`, unbekannte Pfade, Traversalversuche und Schreibmethoden werden abgewiesen. Die nach dem Start verifizierten Bytes bleiben im Speicher, sodass nachträgliche Dateisystemänderungen nicht ungeprüft ausgeliefert werden.

```text
schauwerk-miro-companion-serve \
  --bundle-root /srv/schauwerk-companion/bundle \
  --bind 127.0.0.1 \
  --port 18082
```

Der Start bricht unter anderem ab bei:

- fehlenden, zusätzlichen, symlinkgebundenen oder mehrfach verlinkten Bundledateien;
- abweichenden Datei- oder Receipt-Digests;
- unvollständigem oder Miro-inkompatiblem Headervertrag;
- einer nicht lokalen Bindeadresse.

Der Prozess selbst terminiert kein TLS und darf nicht direkt an ein öffentliches Interface gebunden werden. Eine vorgeschaltete HTTPS-Schicht muss die Backend-Header unverändert weitergeben, Redirects vermeiden und anschließend mit `release-doctor` geprüft werden. Der öffentliche Host gilt erst als freigegeben, wenn zusätzlich der reale Miro-In-Board-Readback gegen dieselbe App-URL bestanden ist.

### Systemd-Beispiel

```ini
[Unit]
Description=Schauwerk Miro Companion
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/schauwerk-miro-companion-serve --bundle-root /srv/schauwerk-companion/bundle --bind 127.0.0.1 --port 18082
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectClock=yes
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
IPAddressDeny=any
IPAddressAllow=localhost
UMask=0077

[Install]
WantedBy=default.target
```

Die konkrete Installation muss den ausführbaren Pfad und die Bundle-Wurzel an einen digestgebundenen, read-only Releasepfad binden. Ein laufender Loopbackdienst allein belegt keine öffentliche Erreichbarkeit und keinen vollständigen Releasevertrag.

## Externe Gates

```text
schauwerk miro companion gate-status --json
```

Die Statusoberfläche trennt vier Gates:

1. öffentliche HTTPS-Bereitstellung;
2. Miro-Developer-App-Registrierung;
3. Installation in das Zielteam;
4. interaktive Autorisierung und In-Board-Readback.

Ohne gebundene Evidenz bleiben diese Gates `not_evidenced`. Ein erfolgreicher lokaler Build, MCP-OAuth oder ein separates REST-Credential dürfen nicht als Web-SDK-Autorisierung ausgelegt werden.

## Miro-Vertrag

Die App benötigt ausschließlich `boards:read`.

Der Launcher prüft `canOpenPanel()`, bevor er `openPanel()` aufruft. Das Panel liest `getInfo()`, `getSelection()` und Frames über `board.get({type: "frame"})`. Der Änderungszeitpunkt stammt aus der dokumentierten Eigenschaft `updatedAt`. Änderungen der Auswahl werden über `selection:update` übernommen. Fokussierung erfolgt lokal über `viewport.zoomTo()`.

Es gibt keine Boardmutation, keinen Miro-OAuth-Token im Bundle, keinen REST-Zugriff und keine Verbindung zum MCP-Tokenbestand.

## Sicherheit

- genau eine externe JavaScript-Abhängigkeit: das offizielle Miro Web SDK;
- keine weiteren externen Skripte oder Styles;
- keine Inline-Skripte, `eval`, `new Function` oder HTML-Injektion;
- Providertexte werden ausschließlich über `textContent` dargestellt;
- Board-ID wird standardmäßig nicht angezeigt;
- maximal 50 ausgewählte Objekte und 200 Frames;
- CSP erlaubt Skripte nur vom eigenen Ursprung und von der exakten SDK-Datei;
- `frame-ancestors` erlaubt ausschließlich Miro;
- Kamera, Mikrofon, Geolocation, Payment und USB sind deaktiviert.

## Deploymentgrenze

Der Build ist deploybar, aber nicht selbstregistrierend. Für einen Livebetrieb muss das Paket unter einer öffentlichen HTTPS-URL mit den geforderten Response-Headern bereitgestellt und diese URL in einer Miro-Developer-App als App-URL konfiguriert werden. Installation, Teamfreigabe und Developer-App-Identität liegen außerhalb des Repositorys und werden nicht aus dem MCP-Login abgeleitet.

Der Standalone-Modus wird nur aktiviert, wenn die Seite nicht in einem Miro-iframe läuft. Er belegt nur die lokale Receipt- und Qualitätsanzeige und keine Miro-Integration. Da das Miro Web SDK providerseitig ausgeliefert wird, belegt der Build weder dessen unveränderlichen Inhalt noch eine lokale Subresource-Integrity-Bindung.
