# Start containers and wait until they're healthy (requires HEALTHCHECK)
docker compose up -d --wait
# Open the UI page
Start-Process "http://localhost:8765/ui/shell.html#/home"
