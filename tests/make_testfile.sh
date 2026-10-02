#!/usr/bin/env bash
# tests/make_testfile.sh - Generate random binary test files for benchmarking
set -euo pipefail

TARGET_DIR="${1:-tests/data}"
mkdir -p "$TARGET_DIR"

FILE_10MB="$TARGET_DIR/test_10mb.bin"
FILE_100MB="$TARGET_DIR/test_100mb.bin"

echo "[*] Generating 10 MB test file: $FILE_10MB ..."
head -c 10485760 /dev/urandom > "$FILE_10MB"
echo "[✔] Created 10 MB file: $(ls -lh "$FILE_10MB" | awk '{print $5}')"

echo "[*] Generating 100 MB test file: $FILE_100MB ..."
head -c 104857600 /dev/urandom > "$FILE_100MB"
echo "[✔] Created 100 MB file: $(ls -lh "$FILE_100MB" | awk '{print $5}')"

echo ""
echo "Files ready in $TARGET_DIR:"
sha256sum "$FILE_10MB"
sha256sum "$FILE_100MB"
