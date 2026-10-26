#!/usr/bin/env bash
# Optional upstream tools bonrs can call. Re-run to update. Nothing here is required.
set -e; cd "$(dirname "$0")"; mkdir -p vendor
[ -d vendor/Auto-Research ] || git clone -q --depth 1 https://github.com/Filtain/Auto-Research vendor/Auto-Research   # multi-source retriever + evidence store (MIT)
[ -d vendor/writing-driven-autoresearch ] || git clone -q --depth 1 https://github.com/happyhappy-jun/writing-driven-autoresearch vendor/writing-driven-autoresearch  # reference prompts/style guide (MIT)
npx -y skills@latest add bahayonghang/academic-writing-skills -y -a claude-code -s "*" --copy 2>/dev/null || echo "skills CLI failed; install manually: npx skills add bahayonghang/academic-writing-skills"
echo "vendor ready"
