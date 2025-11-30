#!/bin/bash
set -e

echo "=============================================="
echo "   Agent Stack — Full Clean Rebuild Script"
echo "=============================================="
echo ""

# Navigate to the root of the repo (directory where docker-compose.yml lives)
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$ROOT_DIR"

echo "Step 1: Stopping running containers..."
docker compose down || true
echo "✓ Containers stopped"
echo ""

echo "Step 2: Removing all per-user agent containers..."
AGENT_CONTAINERS=$(docker ps -aq --filter "name=agent-")

if [ -n "$AGENT_CONTAINERS" ]; then
    docker rm -f $AGENT_CONTAINERS
    echo "✓ Removed agent-* containers"
else
    echo "No agent-* containers found."
fi
echo ""

echo "Step 3: Rebuilding images (no cache)..."
docker compose build --no-cache
echo "✓ Images rebuilt"
echo ""

echo "Step 4: Starting stack..."
docker compose up -d
echo "✓ Stack started"
echo ""

echo "Step 5: Checking dispatcher health..."
sleep 2
curl -s http://localhost:7000/healthz || echo "Dispatcher not responding yet..."
echo ""
echo "=============================================="
echo " Clean rebuild completed successfully!"
echo "=============================================="
echo ""
echo "You can now send a chat request to regenerate user containers:"
echo '  curl -X POST "http://localhost:7000/u/alice/chat?session_id=test" \'
echo '       -H "Content-Type: application/json" \'
echo '       -d "{\"message\": \"hello\"}"'
echo ""
