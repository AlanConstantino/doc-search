#!/bin/bash
# Build search index for a crawled site
# Usage: ./index.sh [URL]

set -e

URL="${1:-}"

if [[ -z "$URL" ]]; then
    read -p "Enter site URL: " URL
fi

if [[ -z "$URL" ]]; then
    echo "Error: URL required"
    exit 1
fi

echo "📚 Building index for: $URL"
echo ""

python3 -m doc_search index "$URL"

echo ""
echo "✅ Done! Now run: ./search.sh $URL \"your query\""
