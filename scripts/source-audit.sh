#!/usr/bin/env bash
set -euo pipefail
BASE="https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10"
for repo in samsung-exynos9820 kernel-samsung-exynos9820; do
  url="$BASE/$repo.git"
  echo "::group::$repo"
  git ls-remote --heads "$url" | sort | tee "${repo}-branches.txt"
  echo "::endgroup::"
done
echo "Audit only. No firmware images were built or flashed."
