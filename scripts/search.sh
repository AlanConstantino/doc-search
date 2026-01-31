#!/bin/bash
# Search a documentation site
# Usage: ./search.sh [URL] [QUERY]

set -e

URL="${1:-}"
QUERY="${2:-}"

if [[ -z "$URL" ]]; then
    read -p "Enter site URL: " URL
fi

if [[ -z "$QUERY" ]]; then
    read -p "Enter search query: " QUERY
fi

if [[ -z "$URL" || -z "$QUERY" ]]; then
    echo "Error: URL and query required"
    exit 1
fi

python3 -m doc_search search "$URL" "$QUERY"
