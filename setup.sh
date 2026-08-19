#!/bin/bash
echo "🚀 Starte Installation der Abhängigkeiten..."
python3 -m pip install -r requirements.txt
python3 -m playwright install
echo "✅ Setup erfolgreich abgeschlossen! Du kannst das Skript jetzt mit 'python3 run.py' starten."