#!/usr/bin/env bash
# Stage the Zenodo upload bundle for a published data release (ADR-0002).
#
# Usage: scripts/stage-zenodo-bundle.sh [TAG] [OUT_DIR]
#   TAG    data-release tag to stage from  (default: v1.0.0-data)
#   OUT    bundle directory, under dist/    (default: dist/zenodo-<version>)
#
# The bundle is exactly four files: the byte-exact artifact trio extracted
# from the TAG (the authority — never the working tree, which may have moved
# on) plus the record README taken from the HEAD blob of
# docs/zenodo/v<version>/record-README.md — committed bytes only, so the
# published bundle is always reproducible from a git object. Every file is
# verified after staging; checksums are printed for the Zenodo cross-check
# recorded in docs/zenodo/v<version>/form-values.md.
set -euo pipefail

TAG="${1:-v1.0.0-data}"
VERSION="${TAG#v}"          # v1.0.0-data -> 1.0.0 (Zenodo version, ADR-0002)
VERSION="${VERSION%-data}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DOCS_README_REL="docs/zenodo/v$VERSION/record-README.md"
OUT="${2:-dist/zenodo-$VERSION}"
ARTIFACTS=(maicdb.sqlite maicdb.sql load-manifest.json)

fail() { echo "stage-zenodo-bundle: $*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || fail "git not found"
# show-ref (not ^{tag}): lightweight tags must work too — a future release
# may tag without -a, and the <tag>:<path> lookups below peel either kind.
git show-ref --verify --quiet "refs/tags/$TAG" ||
    fail "git tag $TAG not found"
for f in "${ARTIFACTS[@]}"; do
    git cat-file -e "$TAG:db/$f" 2>/dev/null || fail "$TAG:db/$f not found"
done
[ -f "$DOCS_README_REL" ] || fail "$DOCS_README_REL not found — draft it first"

# OUT may only be a directory strictly under the repo's dist/ (gitignored
# build output). This refuses tracked directories (db/, docs/, src/ …),
# dist itself, absolute paths elsewhere, trailing slashes, and any '..'
# component — before rm -rf touches anything. (Normalization first: the
# guard patterns are anchored, so "dist/" or an absolute dist path must not
# slip past them.)
OUT="${OUT#./}"
while [ "$OUT" != "${OUT%/}" ]; do OUT="${OUT%/}"; done
case "$OUT" in
    "$REPO_ROOT"/*) OUT="${OUT#"$REPO_ROOT"/}" ;;
esac
case "$OUT" in
    dist/*) : ;;
    *) fail "OUT must be a subdirectory of dist/ (got '$OUT')" ;;
esac
case "/$OUT/" in
    */../* | */./* | "/dist/") fail "OUT must be a directory strictly under dist/, without '.'/'..' components (got '$OUT')" ;;
esac
rm -rf -- "$OUT"
mkdir -p "$OUT"

for f in "${ARTIFACTS[@]}"; do
    git cat-file blob "$TAG:db/$f" > "$OUT/$f"
done
# The record README ships inside an effectively immutable Zenodo record:
# stage the committed (HEAD) bytes, never uncommitted working-tree edits.
git cat-file blob "HEAD:$DOCS_README_REL" > "$OUT/README.md" 2>/dev/null ||
    fail "HEAD:$DOCS_README_REL not found — commit the record README before staging"

# Byte-identity verification — staged files vs their git sources.
for f in "${ARTIFACTS[@]}"; do
    git cat-file blob "$TAG:db/$f" | cmp -s - "$OUT/$f" ||
        fail "$OUT/$f differs from $TAG:db/$f"
done
git cat-file blob "HEAD:$DOCS_README_REL" | cmp -s - "$OUT/README.md" ||
    fail "staged README differs from HEAD:$DOCS_README_REL"

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
    else sha256sum "$1" | cut -d' ' -f1; fi
}
md5_of() {
    if command -v md5 >/dev/null 2>&1; then md5 -q "$1"
    else md5sum "$1" | cut -d' ' -f1; fi
}

echo "Bundle staged: $OUT  ($TAG -> Zenodo version $VERSION)"
echo
echo "File | Bytes | SHA256 | MD5"
echo "--- | --- | --- | ---"
for f in "${ARTIFACTS[@]}" README.md; do
    bytes="$(wc -c < "$OUT/$f" | tr -d ' ')"
    sha="$(sha256_of "$OUT/$f")" || fail "checksum tool failed for $f"
    md5="$(md5_of "$OUT/$f")" || fail "md5 tool failed for $f"
    [ -n "$sha" ] && [ -n "$md5" ] || fail "empty checksum for $f"
    echo "\`$f\` | $bytes | \`$sha\` | \`$md5\`"
done
echo
echo "Upload all four files; cross-check the checksums Zenodo reports after upload."
