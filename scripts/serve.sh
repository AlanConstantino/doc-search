#!/bin/bash
# Start web UI for searching
# Usage: ./serve.sh [URL] [PORT]

set -e

URL="${1:-}"
PORT="${2:-8080}"

if [[ -z "$URL" ]]; then
    read -p "Enter site URL: " URL
fi

if [[ -z "$URL" ]]; then
    echo "Error: URL required"
    exit 1
fi

echo "🌐 Starting web UI on http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

python3 -m doc_search serve "$URL" --port "$PORT" --open
