#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# deploy.sh — Build and assemble web-iterations into web/public/
#
# Only builds/deploys the specific versions you specify.
# Anything not specified is left as-is in web/public/.
#
# Usage:
#   ./web/deploy.sh                                    # interactive
#   ./web/deploy.sh --root ch4/v0                      # root only
#   ./web/deploy.sh --preview ch4/v1                   # preview only (root unchanged)
#   ./web/deploy.sh --root ch4/v0 --preview ch4/v1     # root + previews
# ─────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ITERATIONS_DIR="$REPO_ROOT/web-iterations"
PUBLIC_DIR="$REPO_ROOT/web/public"
STAGING_DIR=""

# Preserved files that survive root cleaning
PRESERVE_FILES=(CNAME robots.txt)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()   { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*" >&2; }

# ─────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────
cleanup() {
  if [[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────

# Check if a version directory has deployable content
has_content() {
  local dir="$1"
  [[ -f "$dir/web/package.json" ]] && return 0
  [[ -f "$dir/package.json" ]] && return 0
  [[ -f "$dir/web/index.html" ]] && return 0
  [[ -f "$dir/index.html" ]] && return 0
  [[ -f "$dir/hugo.toml" ]] && return 0
  [[ -f "$dir/config.toml" ]] && return 0
  return 1
}

# Extract chapter prefix: ch4_alpha_authentic_tool → ch4
extract_chapter_prefix() {
  local name="$1"
  if [[ "$name" =~ ^ch[0-9]+ ]]; then
    local prefix="${name%%_*}"
    echo "$prefix"
  else
    echo ""
  fi
}

# Resolve short path (ch4/v0) to full directory path
resolve_version_dir() {
  local short="$1"  # e.g. ch4/v0
  local chapter="${short%%/*}"  # ch4
  local version="${short##*/}"  # v0

  for chapter_dir in "$ITERATIONS_DIR"/"${chapter}"_*/; do
    [[ -d "$chapter_dir" ]] || continue
    local version_dir="$chapter_dir$version"
    if [[ -d "$version_dir" ]]; then
      echo "$version_dir"
      return 0
    fi
  done

  err "Could not resolve version: $short"
  return 1
}

# Validate a version string — checks it resolves and has content
validate_version() {
  local short="$1"

  # Must match ch{N}/v{N} pattern
  if [[ ! "$short" =~ ^ch[0-9]+/v[0-9] ]]; then
    err "Invalid version format: $short (expected ch{N}/v{N}, e.g. ch4/v0)"
    return 1
  fi

  local version_dir
  version_dir="$(resolve_version_dir "$short")" || return 1

  if ! has_content "$version_dir"; then
    err "Version $short exists but has no deployable content"
    return 1
  fi

  return 0
}

# ─────────────────────────────────────────────────────────────
# Stack detection
# ─────────────────────────────────────────────────────────────
detect_stack() {
  local version_dir="$1"
  local project_root=""

  # Static index.html at version root takes priority over nested build systems
  if [[ -f "$version_dir/index.html" ]]; then
    echo "static|$version_dir"
    return
  fi

  # Check for nested web/ directory with package.json
  if [[ -f "$version_dir/web/package.json" ]]; then
    project_root="$version_dir/web"
  elif [[ -f "$version_dir/package.json" ]]; then
    project_root="$version_dir"
  fi

  if [[ -n "$project_root" ]]; then
    if grep -q '"next"' "$project_root/package.json" 2>/dev/null; then
      echo "nextjs|$project_root"
      return
    fi
    if grep -q '"vite"' "$project_root/package.json" 2>/dev/null; then
      echo "vite|$project_root"
      return
    fi
    if grep -q '"astro"' "$project_root/package.json" 2>/dev/null; then
      echo "astro|$project_root"
      return
    fi
    if grep -q '"build"' "$project_root/package.json" 2>/dev/null; then
      echo "node-generic|$project_root"
      return
    fi
  fi

  if [[ -f "$version_dir/hugo.toml" || -f "$version_dir/config.toml" ]]; then
    echo "hugo|$version_dir"
    return
  fi

  if [[ -f "$version_dir/web/index.html" ]]; then
    echo "static|$version_dir/web"
    return
  fi

  err "Could not detect stack for: $version_dir"
  return 1
}

# ─────────────────────────────────────────────────────────────
# Build functions
# ─────────────────────────────────────────────────────────────

build_static() {
  local source_dir="$1"
  local staging_dir="$2"
  local base_path="$3"

  log "Copying static files"
  # Copy everything except known non-web directories
  rsync -a \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='.git' \
    --exclude='src' \
    --exclude='out' \
    --exclude='dist' \
    --exclude='build' \
    --exclude='web' \
    --exclude='package.json' \
    --exclude='package-lock.json' \
    --exclude='tsconfig.json' \
    --exclude='*.config.*' \
    --exclude='CLAUDE.md' \
    --exclude='README.md' \
    "$source_dir/" "$staging_dir"/
  ok "Static copy complete"
}

build_nextjs() {
  local source_dir="$1"
  local staging_dir="$2"
  local base_path="$3"

  local config_file="$source_dir/next.config.ts"
  if [[ ! -f "$config_file" ]]; then
    for ext in js mjs; do
      if [[ -f "$source_dir/next.config.$ext" ]]; then
        config_file="$source_dir/next.config.$ext"
        break
      fi
    done
  fi

  local config_backup=""
  local build_ok=true

  if [[ -f "$config_file" ]]; then
    config_backup="$config_file.deploy-backup"
    cp "$config_file" "$config_backup"

    if [[ "$base_path" == "/" || -z "$base_path" ]]; then
      sed -i '' 's|basePath:.*,||' "$config_file"
      log "Patched next.config: removed basePath (root deploy)"
    else
      sed -i '' "s|basePath:.*,|basePath: \"$base_path\",|" "$config_file"
      log "Patched next.config: basePath → $base_path"
    fi
  fi

  log "Installing dependencies..."
  (cd "$source_dir" && npm ci --prefer-offline 2>&1 | tail -1) || build_ok=false

  if [[ "$build_ok" == true ]]; then
    log "Building Next.js site..."
    (cd "$source_dir" && npm run build 2>&1 | tail -3) || build_ok=false
  fi

  # Always restore config before checking results
  if [[ -n "$config_backup" && -f "$config_backup" ]]; then
    mv "$config_backup" "$config_file"
  fi

  if [[ "$build_ok" != true ]]; then
    err "Next.js build failed"
    return 1
  fi

  if [[ -d "$source_dir/out" ]]; then
    # Copy build output, filtering Next.js artifacts that aren't needed for deploy
    rsync -a \
      --exclude='__next.*.txt' \
      --exclude='_not-found' \
      --exclude='_not-found.*' \
      --exclude='*.txt' \
      --exclude='*.map' \
      --exclude='_buildManifest.js' \
      --exclude='_ssgManifest.js' \
      --exclude='_clientMiddlewareManifest.json' \
      "$source_dir/out/" "$staging_dir"/

    # Rename _next → assets and rewrite references in HTML/JS
    if [[ -d "$staging_dir/_next" ]]; then
      mv "$staging_dir/_next" "$staging_dir/assets"
      find "$staging_dir" -type f \( -name '*.html' -o -name '*.js' \) \
        -exec sed -i '' 's|/_next/|/assets/|g' {} +
      # Also handle relative references (for preview deploys with basePath)
      find "$staging_dir" -type f \( -name '*.html' -o -name '*.js' \) \
        -exec sed -i '' 's|_next/|assets/|g' {} +
    fi

    ok "Next.js build complete"
  else
    err "Next.js build did not produce out/ directory"
    return 1
  fi
}

build_vite() {
  local source_dir="$1"
  local staging_dir="$2"
  local base_path="$3"

  log "Installing dependencies..."
  (cd "$source_dir" && npm ci --prefer-offline 2>&1 | tail -1)

  log "Building Vite site..."
  if [[ "$base_path" == "/" || -z "$base_path" ]]; then
    (cd "$source_dir" && npm run build 2>&1 | tail -3)
  else
    (cd "$source_dir" && npm run build -- --base "$base_path/" 2>&1 | tail -3)
  fi

  if [[ -d "$source_dir/dist" ]]; then
    cp -R "$source_dir/dist"/* "$staging_dir"/
    ok "Vite build complete"
  else
    err "Vite build did not produce dist/ directory"
    return 1
  fi
}

build_node_generic() {
  local source_dir="$1"
  local staging_dir="$2"
  local base_path="$3"

  log "Installing dependencies..."
  (cd "$source_dir" && npm ci --prefer-offline 2>&1 | tail -1)

  log "Building..."
  (cd "$source_dir" && npm run build 2>&1 | tail -3)

  local output_dir=""
  for candidate in out dist build; do
    if [[ -d "$source_dir/$candidate" ]]; then
      output_dir="$source_dir/$candidate"
      break
    fi
  done

  if [[ -n "$output_dir" ]]; then
    cp -R "$output_dir"/* "$staging_dir"/
    ok "Build complete (output: $(basename "$output_dir")/)"
  else
    err "Build did not produce out/, dist/, or build/ directory"
    return 1
  fi
}

# ─────────────────────────────────────────────────────────────
# Main build dispatcher
# ─────────────────────────────────────────────────────────────
build_version() {
  local short_path="$1"   # e.g. ch4/v0
  local deploy_path="$2"  # e.g. "/" or "/ch4/v1"
  local staging_dir="$3"

  local version_dir
  version_dir="$(resolve_version_dir "$short_path")"

  local detection
  detection="$(detect_stack "$version_dir")"
  local stack="${detection%%|*}"
  local project_root="${detection##*|}"

  local label
  [[ "$deploy_path" == "/" ]] && label="$short_path → /" || label="$short_path → $deploy_path"

  echo ""
  log "Building ${BOLD}$label${NC}  [${stack}]"

  mkdir -p "$staging_dir"

  case "$stack" in
    static)       build_static "$project_root" "$staging_dir" "$deploy_path" ;;
    nextjs)       build_nextjs "$project_root" "$staging_dir" "$deploy_path" ;;
    vite)         build_vite "$project_root" "$staging_dir" "$deploy_path" ;;
    node-generic) build_node_generic "$project_root" "$staging_dir" "$deploy_path" ;;
    *)            err "Unknown stack: $stack"; return 1 ;;
  esac
}

# ─────────────────────────────────────────────────────────────
# Preview index page generator
# ─────────────────────────────────────────────────────────────
generate_preview_index() {
  local previews=("$@")
  local preview_dir="$PUBLIC_DIR/preview"
  mkdir -p "$preview_dir"

  # Build list of all previews in the preview dir (deployed now + previously)
  local all_previews=()
  for preview in "${previews[@]}"; do
    [[ -z "$preview" ]] && continue
    all_previews+=("$preview")
  done
  # Also include any existing preview dirs not in this deploy
  if [[ -d "$preview_dir" ]]; then
    for chapter_dir in "$preview_dir"/ch*/; do
      [[ -d "$chapter_dir" ]] || continue
      local ch_name
      ch_name="$(basename "$chapter_dir")"
      for version_dir in "$chapter_dir"v*/; do
        [[ -d "$version_dir" ]] || continue
        local v_name
        v_name="$(basename "$version_dir")"
        local existing="$ch_name/$v_name"
        # Skip if already in our list
        local found=false
        for p in "${all_previews[@]}"; do
          [[ "$p" == "$existing" ]] && found=true && break
        done
        [[ "$found" == false ]] && all_previews+=("$existing")
      done
    done
  fi

  # Sort
  IFS=$'\n' all_previews=($(printf '%s\n' "${all_previews[@]}" | sort)); unset IFS

  # Generate links
  local links=""
  for p in "${all_previews[@]}"; do
    links+="      <li><a href=\"/preview/$p/\">$p</a></li>"$'\n'
  done

  cat > "$preview_dir/index.html" << INDEXEOF
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>screamingface — previews</title>
  <meta name="robots" content="noindex, nofollow">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>😱</text></svg>">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; font-size: 16px; color: #14121a; background: #faf9fb; padding: 3rem 1.25rem; max-width: 32rem; margin: 0 auto; }
    h1 { font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; }
    p { color: #666; margin-bottom: 2rem; }
    ul { list-style: none; }
    li { margin-bottom: 0.75rem; }
    a { color: #c8842a; text-decoration: underline; text-underline-offset: 2px; font-size: 1.125rem; }
    a:hover { opacity: 0.8; }
    .back { font-size: 0.875rem; margin-top: 2rem; }
    .back a { font-size: 0.875rem; color: #666; }
  </style>
</head>
<body>
  <div style="font-size:2.5rem; margin-bottom:1rem; user-select:none;">😱</div>
  <h1>Previews</h1>
  <p>Site versions for review.</p>
  <ul>
${links}  </ul>
  <div class="back"><a href="/">← back to site</a></div>
</body>
</html>
INDEXEOF

  ok "Preview index page generated"
}

# ─────────────────────────────────────────────────────────────
# Assembly — only touches what was specified
# ─────────────────────────────────────────────────────────────
assemble() {
  local root_version="$1"  # empty string if not specified
  shift
  local preview_versions=("$@")

  # Nothing to do?
  if [[ -z "$root_version" && ${#preview_versions[@]} -eq 0 ]]; then
    warn "Nothing to deploy — no root or preview versions specified"
    return 0
  fi

  STAGING_DIR="$(mktemp -d)"

  # Build root version (if specified)
  if [[ -n "$root_version" ]]; then
    local root_staging="$STAGING_DIR/root"
    mkdir -p "$root_staging"
    build_version "$root_version" "/" "$root_staging"
  fi

  # Build preview versions
  for preview in ${preview_versions[@]+"${preview_versions[@]}"}; do
    [[ -z "$preview" ]] && continue
    local preview_staging="$STAGING_DIR/$preview"
    mkdir -p "$preview_staging"
    build_version "$preview" "/preview/$preview" "$preview_staging"
  done

  echo ""
  log "Assembling into web/public/..."

  # Deploy root (if specified) — clean root-level files, preserve subdirs & special files
  if [[ -n "$root_version" ]]; then
    local root_staging="$STAGING_DIR/root"

    # Preserve CNAME, robots.txt
    local preserve_dir="$STAGING_DIR/_preserved"
    mkdir -p "$preserve_dir"
    for f in "${PRESERVE_FILES[@]}"; do
      if [[ -f "$PUBLIC_DIR/$f" ]]; then
        cp "$PUBLIC_DIR/$f" "$preserve_dir/$f"
      fi
    done

    # Remove everything except the preview directory
    for item in "$PUBLIC_DIR"/*; do
      [[ -e "$item" ]] || continue
      local name
      name="$(basename "$item")"
      [[ -d "$item" && "$name" == "preview" ]] && continue
      rm -rf "$item"
    done
    # Also clean dotfiles from previous builds
    rm -rf "$PUBLIC_DIR"/.next 2>/dev/null

    # Copy new root
    cp -R "$root_staging"/* "$PUBLIC_DIR"/

    # Restore preserved files
    for f in "${PRESERVE_FILES[@]}"; do
      if [[ -f "$preserve_dir/$f" ]]; then
        cp "$preserve_dir/$f" "$PUBLIC_DIR/$f"
      fi
    done
  fi

  # Deploy previews (if specified) — into preview/ subdirectory
  local has_previews=false
  for preview in ${preview_versions[@]+"${preview_versions[@]}"}; do
    [[ -z "$preview" ]] && continue
    has_previews=true
    local preview_staging="$STAGING_DIR/$preview"
    local target_dir="$PUBLIC_DIR/preview/$preview"

    # Clean existing preview dir if it exists
    if [[ -d "$target_dir" ]]; then
      rm -rf "$target_dir"
    fi

    mkdir -p "$target_dir"
    cp -R "$preview_staging"/* "$target_dir"/
  done

  # Generate preview index page listing all deployed previews
  if [[ "$has_previews" == true ]]; then
    generate_preview_index ${preview_versions[@]+"${preview_versions[@]}"}
  fi

  echo ""
  ok "Assembled into web/public/"

  # Verification — only check what was deployed
  verify_output "$root_version" ${preview_versions[@]+"${preview_versions[@]}"}

  echo ""
  echo -e "${BOLD}Review the output and commit when ready.${NC}"
  echo "  Preview locally: npx serve web/public"
}

# ─────────────────────────────────────────────────────────────
# Verification — only checks what was deployed
# ─────────────────────────────────────────────────────────────
verify_output() {
  local root_version="$1"
  shift
  local preview_versions=("$@")

  echo ""
  log "Verifying output..."

  # Check root (only if we deployed it)
  if [[ -n "$root_version" ]]; then
    if [[ -f "$PUBLIC_DIR/index.html" ]]; then
      ok "Root index.html present"
      if ! grep -qi 'noindex' "$PUBLIC_DIR/index.html" 2>/dev/null; then
        warn "Root index.html missing noindex meta tag"
      fi
    else
      warn "Missing root index.html!"
    fi
  fi

  # Check each preview we deployed
  for preview in ${preview_versions[@]+"${preview_versions[@]}"}; do
    [[ -z "$preview" ]] && continue
    if [[ -f "$PUBLIC_DIR/preview/$preview/index.html" ]]; then
      ok "Preview preview/$preview/index.html present"
      if ! grep -qi 'noindex' "$PUBLIC_DIR/preview/$preview/index.html" 2>/dev/null; then
        warn "preview/$preview/index.html missing noindex meta tag"
      fi
    else
      warn "Missing preview/$preview/index.html!"
    fi
  done

  # Check preview index
  if [[ -f "$PUBLIC_DIR/preview/index.html" ]]; then
    ok "Preview index page present"
  fi

  # Check CNAME
  if [[ -f "$PUBLIC_DIR/CNAME" ]]; then
    ok "CNAME preserved"
  else
    warn "CNAME missing!"
  fi
}

# ─────────────────────────────────────────────────────────────
# Interactive mode — only scans/detects what user specifies
# ─────────────────────────────────────────────────────────────
interactive() {
  echo -e "${BOLD}screamingface deploy${NC}"
  echo ""
  echo "Enter versions as ch{N}/v{N} (e.g. ch4/v0)"
  echo ""

  # Ask for root
  read -rp "Version for root (screamingface.ai/), or Enter to skip: " root_choice
  root_choice="$(echo "$root_choice" | xargs)"  # trim

  if [[ -n "$root_choice" ]]; then
    if ! validate_version "$root_choice"; then
      exit 1
    fi
    local root_dir
    root_dir="$(resolve_version_dir "$root_choice")"
    local root_detection
    root_detection="$(detect_stack "$root_dir")"
    local root_stack="${root_detection%%|*}"
    ok "$root_choice [${root_stack}]"
  else
    log "Skipping root — existing root files will be kept"
  fi

  echo ""
  read -rp "Versions for previews (comma-separated), or Enter to skip: " preview_input
  preview_input="$(echo "$preview_input" | xargs)"  # trim

  local preview_list=()
  if [[ -n "$preview_input" ]]; then
    IFS=',' read -ra raw_previews <<< "$preview_input"
    for p in "${raw_previews[@]}"; do
      p="$(echo "$p" | xargs)"  # trim whitespace
      [[ -z "$p" ]] && continue
      # If they just typed "v1" and we have a root chapter context, expand it
      if [[ "$p" =~ ^v[0-9] && -n "$root_choice" ]]; then
        p="${root_choice%%/*}/$p"
      fi
      if validate_version "$p"; then
        local pdir
        pdir="$(resolve_version_dir "$p")"
        local pdetection
        pdetection="$(detect_stack "$pdir")"
        local pstack="${pdetection%%|*}"
        ok "$p [${pstack}]"
        preview_list+=("$p")
      else
        warn "Skipping $p"
      fi
    done
  else
    log "Skipping previews — existing preview directories will be kept"
  fi

  echo ""
  assemble "$root_choice" ${preview_list[@]+"${preview_list[@]}"}
}

# ─────────────────────────────────────────────────────────────
# CLI argument parsing
# ─────────────────────────────────────────────────────────────
main() {
  local root_version=""
  local preview_versions=()

  if [[ $# -eq 0 ]]; then
    interactive
    exit 0
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --root)
        root_version="$2"
        shift 2
        ;;
      --preview)
        preview_versions+=("$2")
        shift 2
        ;;
      --help|-h)
        echo "Usage: ./web/deploy.sh [--root VERSION] [--preview VERSION]..."
        echo ""
        echo "Options:"
        echo "  --root VERSION      Version to deploy at root (e.g. ch4/v0)"
        echo "                      If omitted, existing root is left as-is"
        echo "  --preview VERSION   Version to deploy as preview (repeatable)"
        echo "                      If omitted, existing previews are left as-is"
        echo "  --help              Show this help"
        echo ""
        echo "Examples:"
        echo "  ./web/deploy.sh --root ch4/v0                  # deploy root only"
        echo "  ./web/deploy.sh --preview ch4/v1               # deploy preview only"
        echo "  ./web/deploy.sh --root ch4/v0 --preview ch4/v1 # both"
        echo ""
        echo "Without arguments, runs in interactive mode."
        exit 0
        ;;
      *)
        err "Unknown argument: $1"
        exit 1
        ;;
    esac
  done

  # Validate specified versions
  if [[ -n "$root_version" ]]; then
    validate_version "$root_version" || exit 1
  fi
  for p in ${preview_versions[@]+"${preview_versions[@]}"}; do
    validate_version "$p" || exit 1
  done

  if [[ -z "$root_version" && ${#preview_versions[@]} -eq 0 ]]; then
    err "Nothing to deploy — specify --root and/or --preview"
    exit 1
  fi

  assemble "$root_version" ${preview_versions[@]+"${preview_versions[@]}"}
}

main "$@"
