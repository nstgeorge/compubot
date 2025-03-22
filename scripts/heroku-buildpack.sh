#!/bin/bash

# Exit on error
set -e

# Install Opus library
echo "Installing Opus library..."
apt-get update
apt-get install -y libopus0 libopus-dev

# Apply our patches
echo "Applying patches..."
./scripts/apply_patches.sh

echo "Buildpack setup complete!" 