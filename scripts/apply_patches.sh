#!/bin/bash

# Exit on error
set -e

# Get the virtual environment path
VENV_PATH="${VIRTUAL_ENV:-venv}"

# Find the interactions package directory
INTERACTIONS_DIR=$(find "$VENV_PATH/lib" -type d -name "interactions" | head -n 1)

if [ -z "$INTERACTIONS_DIR" ]; then
    echo "Error: Could not find interactions package directory"
    exit 1
fi

# Apply patches
echo "Applying patches..."
for patch in patches/*.patch; do
    if [ -f "$patch" ]; then
        echo "Applying patch: $patch"
        # Use -p1 to strip the first path component (venv/lib/pythonX.X/site-packages)
        patch -p1 -d "$INTERACTIONS_DIR" < "$patch"
    fi
done

echo "Patches applied successfully!" 