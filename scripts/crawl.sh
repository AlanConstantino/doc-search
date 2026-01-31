#!/bin/bash
# Crawl a documentation site
# Usage: ./crawl.sh [URL] [--pdf]

set -e

URL="${1:-}"
PDF_FLAG=""

# Check for --pdf flag
for arg in "$@"; do
    if [[ "$arg" == "--pdf" ]]; then
        PDF_FLAG="--extract-docs"
    fi
done

# Prompt for URL if not provided
if [[ -z "$URL" || "$URL" == "--pdf" ]]; then
    read -p "Enter URL to crawl: " URL
fi

if [[ -z "$URL" ]]; then
    echo "Error: URL required"
    exit 1
fi

echo "🕷️  Crawling: $URL"
[[ -n "$PDF_FLAG" ]] && echo "📄 PDF extraction enabled"
echo ""

python3 -m doc_search crawl "$URL" \
    --delay 1.0 \
    --workers 1 \
    $PDF_FLAG

echo ""
echo "✅ Done! Now run: ./index.sh $URL"
