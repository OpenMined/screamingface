#!/bin/bash
# Build and preview selected chapter versions locally.
# Usage: ./preview.sh v0 v3 v5
#        ./preview.sh all
#        ./preview.sh        (serves existing previews without rebuilding)

CHAPTER="ch4_alpha_authentic_tool"
ITERATIONS_DIR="web-iterations/$CHAPTER"
PREVIEWS_DIR="web/previews/ch4"
PORT="${PORT:-3000}"

if [ "$1" = "all" ]; then
  set -- $(ls "$ITERATIONS_DIR" | sort)
fi

# Build and copy requested versions
if [ $# -gt 0 ]; then
  for version in "$@"; do
    src="$ITERATIONS_DIR/$version/web"
    if [ ! -d "$src" ]; then
      echo "⚠ $version not found at $src, skipping"
      continue
    fi
    echo "Building $version..."
    (cd "$src" && npm run build --silent 2>&1 | tail -1)
    if [ $? -eq 0 ]; then
      mkdir -p "$PREVIEWS_DIR/$version"
      rm -rf "$PREVIEWS_DIR/$version"
      cp -r "$src/out" "$PREVIEWS_DIR/$version"
      echo "  ✓ $version → $PREVIEWS_DIR/$version"
    else
      echo "  ✗ $version build failed"
    fi
  done
  echo ""
fi

# Show what's available
echo "Previews available:"
for dir in "$PREVIEWS_DIR"/*/; do
  [ -d "$dir" ] && echo "  http://localhost:$PORT/ch4/$(basename "$dir")/"
done

echo ""
echo "Starting server on port $PORT..."
npx serve web/previews -l "$PORT"
