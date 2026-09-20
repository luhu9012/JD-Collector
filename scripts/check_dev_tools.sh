#!/usr/bin/env bash
set -e

echo "Checking macOS developer tools (lightweight Command Line Tools preferred)..."

# Check xcrun
if command -v xcrun >/dev/null 2>&1; then
  if xcrun --version >/dev/null 2>&1; then
    echo "xcrun appears functional:"
    xcrun --version
    exit 0
  fi
fi

# Check xcode-select path
if xcode-select -p >/dev/null 2>&1; then
  echo "xcode-select reports a path: $(xcode-select -p)"
  echo "But xcrun failed — try switching to Command Line Tools (if installed):"
  echo "  sudo xcode-select --switch /Library/Developer/CommandLineTools"
  echo "Or install CLT with: xcode-select --install"
  exit 1
fi

# No path
echo "No developer path found. Recommended minimal step: install Command Line Tools."
echo "Run the following and follow macOS prompts:"
echo "  xcode-select --install"

exit 2
