#!/bin/bash
# Interactive search mode
# Usage: ./interactive.sh [URL]

set -e

URL="${1:-}"

if [[ -z "$URL" ]]; then
    read -p "Enter site URL: " URL
fi

if [[ -z "$URL" ]]; then
    echo "Error: URL required"
    exit 1
fi

python3 -m doc_search interactive "$URL"
