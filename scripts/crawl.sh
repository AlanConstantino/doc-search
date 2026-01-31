#!/bin/bash
# Crawl a documentation site
# Usage: ./crawl.sh [URL] [--pdf] [--same-path] [--incremental]

set -e

URL="${1:-}"
PDF_FLAG=""
SAME_PATH_FLAG=""
INCREMENTAL_FLAG=""

# Check for flags
for arg in "$@"; do
    if [[ "$arg" == "--pdf" ]]; then
        PDF_FLAG="--extract-docs"
    fi
    if [[ "$arg" == "--same-path" ]]; then
        SAME_PATH_FLAG="--same-path"
    fi
    if [[ "$arg" == "--incremental" || "$arg" == "-i" ]]; then
        INCREMENTAL_FLAG="--incremental"
    fi
done

# Prompt for URL if not provided
if [[ -z "$URL" || "$URL" == "--"* ]]; then
    read -p "Enter URL to crawl: " URL
fi

if [[ -z "$URL" ]]; then
    echo "Error: URL required"
    exit 1
fi

echo "🕷️  Crawling: $URL"
[[ -n "$PDF_FLAG" ]] && echo "📄 PDF extraction enabled"
[[ -n "$SAME_PATH_FLAG" ]] && echo "📁 Staying within starting path"
[[ -n "$INCREMENTAL_FLAG" ]] && echo "🔄 Incremental mode (only changed pages)"
echo ""

python3 -m doc_search crawl "$URL" \
    --delay 1.0 \
    --workers 1 \
    $PDF_FLAG \
    $SAME_PATH_FLAG \
    $INCREMENTAL_FLAG

echo ""
echo "✅ Done! Now run: ./index.sh $URL"
