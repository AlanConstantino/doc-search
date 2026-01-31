#!/bin/bash
# One-shot: Crawl + Index a site
# Usage: ./setup.sh [URL] [--pdf]

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

echo "🚀 Setting up doc-search for: $URL"
[[ -n "$PDF_FLAG" ]] && echo "📄 PDF extraction enabled"
echo ""

# Crawl
echo "Step 1/2: Crawling..."
python3 -m doc_search crawl "$URL" \
    --delay 1.0 \
    --workers 1 \
    $PDF_FLAG

echo ""

# Index
echo "Step 2/2: Building index..."
python3 -m doc_search index "$URL"

echo ""
echo "✅ All done! You can now:"
echo "   ./search.sh $URL \"your query\""
echo "   ./serve.sh $URL"
echo "   ./interactive.sh $URL"
