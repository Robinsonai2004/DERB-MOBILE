#!/usr/bin/env bash
# DERB MOBILE - first-time push to GitHub.
#
# Usage (in Termux, inside ~/DERB-Mobile):
#   bash scripts/first-push.sh <your-github-username> [repo-name]
#
# Create the empty repo first at https://github.com/new
#   * Repository name: DERB-Mobile (or pass another name as the 2nd argument)
#   * Leave "Add a README", ".gitignore" and "license" UNCHECKED -
#     this repo already has its history.
#
# When git asks for a password, paste a Personal Access Token, NOT your
# GitHub password:
#   GitHub -> Settings -> Developer settings -> Personal access tokens
#   -> Tokens (classic) -> Generate new token -> tick the "repo" scope.
#
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/first-push.sh <github-username> [repo-name]"
  echo "       repo-name defaults to DERB-Mobile"
  exit 1
fi

USERNAME="$1"
REPO="${2:-DERB-Mobile}"
REMOTE_URL="https://github.com/${USERNAME}/${REPO}.git"

echo "DERB MOBILE -> GitHub first push"
echo "  remote : ${REMOTE_URL}"
echo "  branch : main"
echo

# Reuse an existing origin if there is one, otherwise add it.
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
  echo "origin updated."
else
  git remote add origin "${REMOTE_URL}"
  echo "origin added."
fi

echo
echo "Pushing. When prompted:"
echo "  Username: ${USERNAME}"
echo "  Password: paste your Personal Access Token (not your GitHub password)"
echo
git push -u origin main

echo
echo "Done. Your code is at: https://github.com/${USERNAME}/${REPO}"
