#!/usr/bin/env bash
set -euo pipefail

# Adds submodules for: GA1.1-1.8, GA2.1-2.8, PA1.1-1.8, PA2.1-2.8, WS1.1-1.8, WS2.1-2.8
groups=(GA WS)
series=(1 2)

failed=()

for group in "${groups[@]}"; do
  for s in "${series[@]}"; do
    for i in {1..8}; do
      target="${group}${s}.${i}"
      url="https://github.com/MUDE-2026/${target}.git"
      path="book/assignments/${target}"

      echo "Adding submodule ${target} ..."
      if ! git submodule add -b assignment "${url}" "${path}"; then
        failed+=("${target}")
      fi
    done
  done
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "Completed with failures on:" >&2
  for target in "${failed[@]}"; do
    echo " - ${target}" >&2
  done
  exit 1
fi

echo "All submodules added successfully."
