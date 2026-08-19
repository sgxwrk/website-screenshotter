#!/bin/bash
echo "🚀 Installing dependencies..."
python3 -m pip install -r requirements.txt
python3 -m playwright install
echo "✅ Setup complete! You can now start the script with 'python3 run.py <url>'."