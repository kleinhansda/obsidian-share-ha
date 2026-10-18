# Obsidian Share für Home Assistant

Custom Integration, die Notizen aus einem Obsidian-Vault auf dem Home-Assistant-Host

- als **öffentlichen Nur-Lese-Link** teilt (optional mit Ablaufdatum) und
- in einem **Seitenleisten-Panel** lesbar und bearbeitbar macht (hinter dem HA-Login, mit Rechten pro Nutzer).

Gedacht als selbst gehostete Alternative zu Share-Diensten: kein zusätzlicher Container, kein Reverse Proxy, die Links laufen über die externe URL von Home Assistant.

## Funktionen

- Freigabe per Frontmatter `ha_share: true`. Flag entfernen beendet die Freigabe sofort.
- Links enthalten einen AES-GCM-verschlüsselten Token (Pfad und Ablauf sind nicht sichtbar, nichts wird gespeichert).
- Aktion `obsidian_share.rotate_key` widerruft alle Links auf einmal.
- Aktion `obsidian_share.get_link` für Automationen und Skripte (liefert die URL als Antwort).
- Panel: Notizbaum mit Suche, gerenderte Ansicht mit Inhaltsverzeichnis, Callouts, Wikilinks, eingebetteten Bildern und Aufgaben, Editor mit Konflikterkennung.
- Rechte: Admins dürfen alles, weitere Nutzer als „bearbeiten“ oder „nur lesen“ eintragbar, alle anderen haben keinen Zugriff.

## Installation (HACS)

1. HACS → Menü (⋮) → **Benutzerdefinierte Repositories** → `https://github.com/kleinhansda/obsidian-share-ha`, Typ **Integration**.
2. „Obsidian Share“ installieren und Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Obsidian Share** → Vault-Pfad angeben (Standard `/share/syncthing/obsidian_vault`).
4. Optional in den Optionen: Bearbeiter, Leser und eine abweichende externe URL für Links.

> [!WARNING]
> Wenn die Integration vorher manuell nach `/config/custom_components/obsidian_share/` kopiert wurde, ersetzt HACS diesen Ordner vollständig. Vorher ein HA-Backup anlegen. Der Schlüssel für die Links liegt in `.storage/obsidian_share.key` und bleibt erhalten, bestehende Links funktionieren also weiter.

## Benutzung

Im Panel „Obsidian“ eine Notiz öffnen → **Teilen …** → Gültigkeit wählen → Link kopieren.

Per Aktion:

```yaml
action: obsidian_share.get_link
data:
  path: Projekte/Beispiel.md
  days: 30
response_variable: link
```

Die Notiz muss dafür `ha_share: true` im Frontmatter haben.

## Sicherheit

Der öffentliche Endpunkt `/api/obsidian_share/s/<token>` ist ohne Login erreichbar. Deshalb:

- nur GET, nur Notizen mit `ha_share: true`
- Pfade strikt auf den Vault begrenzt, versteckte Ordner (`.obsidian`, `.trash`, `.stfolder`) und Symlinks nach außen unsichtbar
- ungültige, abgelaufene und nicht freigegebene Links liefern dieselbe 404-Seite
- Bilder nur, wenn die freigegebene Notiz sie selbst einbettet, adressiert per Index
- Roh-HTML in Notizen wird nie ausgegeben, `%%Kommentare%%` werden entfernt, externe Bilder nicht nachgeladen
- CSP ohne Skripte, SVGs in einer CSP-Sandbox, `Referrer-Policy: no-referrer`, `noindex`

## Hinweise zu Syncthing

Beim Speichern schreibt die Integration atomar über eine Temp-Datei `.os-*.tmp` im selben Ordner. Damit Syncthing diese nicht mitsynchronisiert, in die `.stignore` des Vaults eintragen:

```
.os-*.tmp
```

Empfohlen außerdem: Dateiversionierung für den Vault-Ordner in Syncthing aktivieren.

## Entwicklung

```bash
pip install pytest pyyaml cryptography markdown-it-py mdit-py-plugins
pytest -q tests
```

Die Tests decken Token, Vault-Abschottung, Frontmatter und Rendering ab und laufen ohne Home Assistant.

## Lizenz

MIT
