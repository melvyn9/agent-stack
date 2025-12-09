#!/bin/bash
set -e

echo "=== Updating system ==="
sudo apt-get update -y
sudo apt-get upgrade -y

echo "=== Installing prerequisites ==="
sudo apt-get install -y ca-certificates curl gnupg lsb-release unzip jq

echo "=== Installing Docker repository key ==="
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "=== Installing Docker Engine + Compose ==="
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== Adding current user to docker group ==="
sudo usermod -aG docker $USER

echo ""
echo "============================================================"
echo " Docker installed successfully."
echo " IMPORTANT: You MUST now run:  newgrp docker "
echo " OR log out and SSH back in for Docker permissions to apply."
echo "============================================================"
echo ""

echo "=== Installing AWS CLI ==="
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

echo "Setup complete!"
