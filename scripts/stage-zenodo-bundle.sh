#!/usr/bin/env bash
# Stage the Zenodo upload bundle for a published data release (ADR-0002).
#
# Usage: scripts/stage-zenodo-bundle.sh [TAG] [OUT_DIR]
#   TAG    data-release tag to stage from  (default: v1.0.0-data)
#   OUT    bundle directory                (default: dist/zenodo-<version>)
#
# The bundle is exactly four files: the byte-exact artifact trio extracted
# from the TAG (the authority — never the working tree, which may have moved
# on) plus the record README copied from docs/zenodo/v<version>/record-README.md.
# Every file is verified after staging; checksums are printed for the
# Zenodo cross-check recorded in docs/zenodo/v<version>/form-values.md.
set -euo pipefail

TAG="${1:-v1.0.0-data}"
VERSION="${TAG#v}"          # v1.0.0-data -> 1.0.0 (Zenodo version, ADR-0002)
VERSION="${VERSION%-data}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DOCS_DIR="docs/zenodo/v$VERSION"
OUT="${2:-dist/zenodo-$VERSION}"
ARTIFACTS=(maicdb.sqlite maicdb.sql load-manifest.json)

fail() { echo "stage-zenodo-bundle: $*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || fail "git not found"
git cat-file -e "$TAG^{tag}" 2>/dev/null || fail "git tag $TAG not found"
for f in "${ARTIFACTS[@]}"; do
    git cat-file -e "$TAG:db/$f" 2>/dev/null || fail "$TAG:db/$f not found"
done
[ -f "$DOCS_DIR/record-README.md" ] ||
    fail "$DOCS_DIR/record-README.md not found — draft it first"

case "$OUT" in
    ""|"/"|".") fail "refusing unsafe OUT='$OUT'" ;;
    ../*|*/../*) fail "refusing OUT outside the repo: '$OUT'" ;;
esac
rm -rf "$OUT"
mkdir -p "$OUT"

for f in "${ARTIFACTS[@]}"; do
    git cat-file blob "$TAG:db/$f" > "$OUT/$f"
done
cp "$DOCS_DIR/record-README.md" "$OUT/README.md"

# Byte-identity verification — staged files vs the tag blobs.
for f in "${ARTIFACTS[@]}"; do
    git cat-file blob "$TAG:db/$f" | cmp -s - "$OUT/$f" ||
        fail "$OUT/$f differs from $TAG:db/$f"
done
cmp -s "$DOCS_DIR/record-README.md" "$OUT/README.md" ||
    fail "staged README differs from $DOCS_DIR/record-README.md"

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
    echo "\`$f\` | $(wc -c < "$OUT/$f" | tr -d ' ') | \`$(sha256_of "$OUT/$f")\` | \`$(md5_of "$OUT/$f")\`"
done
echo
echo "Upload all four files; cross-check the checksums Zenodo reports after upload."
