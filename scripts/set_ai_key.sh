#!/data/data/com.termux/files/usr/bin/bash
# ==========================================================================
# DERB MOBILE - save your AI provider key privately
#
# Usage:  bash scripts/set_ai_key.sh [provider]
#         provider defaults to "gemini" (the other option is "openai-images")
#
# The key is read with `read -s`, so it is NOT echoed, NOT written to your
# shell history, and NOT printed by this script. It is saved to `.env.local`,
# which git ignores. The value is never passed as a command argument (arguments
# are visible in `ps`), only through a hidden prompt.
# ==========================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

PROVIDER="${1:-gemini}"
ENV_FILE=".env.local"

case "$PROVIDER" in
  gemini|openai-images) ;;
  *)
    echo "Unknown provider '$PROVIDER'. Use 'gemini' or 'openai-images'."
    exit 1
    ;;
esac

# Refuse to write a secret into a file git would actually commit.
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  if ! git check-ignore -q "$ENV_FILE"; then
    echo "ERROR: $ENV_FILE is not ignored by git. Refusing to write a key there."
    echo "Add '$ENV_FILE' to .gitignore first."
    exit 1
  fi
fi

printf 'Paste your %s API key and press Enter (input is hidden): ' "$PROVIDER"
read -rs KEY
printf '\n'

if [ -z "${KEY:-}" ]; then
  echo "No key entered. Nothing changed."
  exit 1
fi

umask 077
{
  printf '%s\n' '# DERB MOBILE - local secrets. NEVER COMMIT (gitignored).'
  printf '%s\n' '# Written by scripts/set_ai_key.sh - safe to delete or edit.'
  printf '%s\n' "DERB_AI_PROVIDER=$PROVIDER"
  printf '%s\n' "DERB_AI_API_KEY=$KEY"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset KEY

echo "Saved to $ENV_FILE (permissions 600)."
echo "The key was not shown, not logged, and git ignores this file."
echo "Start the app with:  bash start.sh"
echo "Check it works in the app via Settings -> Check AI connection."
