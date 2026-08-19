# Website Auto-Screenshotter 📸

Ein automatisierter Web-Crawler auf Python-Basis, der eine Website von einer Start-URL aus durchsucht (crawlt) und von jeder gefundenen Unterseite automatisch einen Full-Page-Screenshot erstellt.

## 🌟 Features

* **Parallel:** Crawlt mehrere Seiten gleichzeitig (konfigurierbar über `--concurrency`).
* **Automatisch & Vollständig:** Speichert die gesamte Länge der Webseite (auch Scroll-Bereiche).
* **Organisierte Struktur:** Speichert Screenshots pro Domain automatisch in eigenen Unterordnern (z. B. `screenshots/example_com/`).
* **Lazy-Loading Support:** Automatisches Scrollen sorgt dafür, dass nachgeladene Bilder mit erfasst werden.
* **Saubere, eindeutige Dateinamen:** Konvertiert URLs automatisch in gültige Bildnamen; Query-Parameter werden per Hash eindeutig gehalten.
* **robots.txt-Respekt:** Beachtet standardmäßig `robots.txt` der Zielseite (kann mit `--ignore-robots` deaktiviert werden).
* **Höflich:** Kleine Pause zwischen Requests (`--delay`) und optionales Blocken von Tracking-/Ads-Requests, um die Zielseite nicht unnötig zu belasten.
* **Loop-Schutz:** Erkennt bereits besuchte bzw. geplante Seiten automatisch.

## ⚠️ Hinweis

Bitte crawle nur Websites, für die du dazu berechtigt bist (eigene Seiten oder mit Erlaubnis). Das Tool respektiert standardmäßig `robots.txt`, ersetzt aber keine rechtliche Prüfung der Nutzungsbedingungen der Zielseite.

---

## 🛠️ Installation

### 1. Repository öffnen

```bash
cd website-screenshotter
```

### 2. Abhängigkeiten installieren

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install
```

### Alternative: Setup-Skript nutzen

Unter macOS/Linux kann stattdessen direkt das mitgelieferte Bash-Skript `setup.sh` genutzt werden:

```bash
chmod +x setup.sh && ./setup.sh
```

## 🚀 Nutzung

```bash
python3 run.py https://example.com
```

### Optionen

| Flag | Standard | Beschreibung |
|---|---|---|
| `--max-pages` | 50 | Maximale Anzahl zu crawlender Seiten |
| `--concurrency` | 3 | Anzahl paralleler Browser-Tabs |
| `--delay` | 0.5 | Pause in Sekunden zwischen Requests pro Worker |
| `--timeout` | 30 | Timeout pro Seite in Sekunden |
| `--output-dir` | screenshots | Basis-Ausgabeordner |
| `--ignore-robots` | aus | `robots.txt` ignorieren (nicht empfohlen) |
| `--no-block-trackers` | aus | Bekannte Tracking-/Ads-Requests nicht blockieren |

Beispiel mit höherer Parallelität und mehr Seiten:

```bash
python3 run.py https://example.com --max-pages 100 --concurrency 5
```
