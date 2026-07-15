# Miro Web SDK Companion v1

Stand: 15. Juli 2026

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
```

Der Builder akzeptiert ausschließlich das Schema `schauwerk-miro-web-sdk-companion.v1`. Ein vorhandenes oder symlinkgebundenes Ziel wird abgewiesen. Das Ergebnis enthält:

- `index.html` als Miro-App-Einstieg;
- `panel.html` als Boardpanel;
- lokale Anwendungs-JavaScript- und CSS-Dateien;
- das offizielle Miro Web SDK wird zur Laufzeit ausschließlich von `https://miro.com/app/static/sdk/v2/miro.js` geladen;
- eine normalisierte `config.json`;
- statische Security-Header;
- einen SHA-256-gebundenen `build-receipt.json`.

Eine bestehende Ausgabe wird mit folgendem Befehl vollständig rückgelesen:

```text
schauwerk miro companion check /tmp/schauwerk-miro-companion
```

## Miro-Vertrag

Die App benötigt ausschließlich `boards:read`.

Der Launcher prüft `canOpenPanel()`, bevor er `openPanel()` aufruft. Das Panel liest `getInfo()`, `getSelection()` und Frames über `board.get({type: "frame"})`. Der Änderungszeitpunkt stammt aus der dokumentierten Eigenschaft `updatedAt`. Änderungen der Auswahl werden über `selection:update` übernommen. Fokussierung erfolgt lokal über `viewport.zoomTo()`.

Es gibt keine Boardmutation, keinen Miro-OAuth-Token im Bundle, keinen REST-Zugriff und keine Verbindung zum MCP-Tokenbestand.

## Sicherheit

- genau eine externe JavaScript-Abhängigkeit: das offizielle Miro Web SDK; keine weiteren externen Skripte oder Styles;
- keine Inline-Skripte, `eval`, `new Function` oder HTML-Injektion;
- Providertexte werden ausschließlich über `textContent` dargestellt;
- Board-ID wird standardmäßig nicht angezeigt;
- maximal 50 ausgewählte Objekte und 200 Frames;
- CSP erlaubt Skripte nur vom eigenen Ursprung und von der exakten SDK-Datei `https://miro.com/app/static/sdk/v2/miro.js`; Stile, Bilder und Verbindungen bleiben auf den eigenen Ursprung begrenzt;
- `frame-ancestors` erlaubt ausschließlich Miro;
- Kamera, Mikrofon, Geolocation, Payment und USB sind deaktiviert.

## Deploymentgrenze

Der Build ist deploybar, aber nicht selbstregistrierend. Für einen Livebetrieb muss das Paket unter einer öffentlichen HTTPS-URL bereitgestellt und diese URL in einer Miro-Developer-App als App-URL konfiguriert werden. Installation, Teamfreigabe und Developer-App-Identität liegen außerhalb des Repositorys und werden nicht aus dem MCP-Login abgeleitet.

Der Standalone-Modus wird nur aktiviert, wenn die Seite nicht in einem Miro-iframe läuft; das bloße Vorhandensein des geladenen SDK genügt nicht als Integrationsbeleg. Er belegt nur die lokale Receipt- und Qualitätsanzeige und keine Miro-Integration. Da das Miro Web SDK providerseitig ausgeliefert wird, belegt der Build weder dessen unveränderlichen Inhalt noch eine lokale Subresource-Integrity-Bindung.
