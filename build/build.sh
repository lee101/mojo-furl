#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/dist"
mojo build --emit shared-lib "$repo_root/src/furl.mojo" \
  -o "$repo_root/dist/libmojo-furl.so"
cp "$repo_root/dist/libmojo-furl.so" "$repo_root/python/mojofurl/libmojo-furl.so"
