<p align="center">
  <img src="backup/static/backup/img/logo.png" alt="Pi-hole Checkpoint" width="200">
</p>

# Pi-hole Checkpoint

A web application for backing up Pi-hole v6 instances via the Teleporter API. Runs as a single Docker container with a web UI and automated scheduler.

**Requires Pi-hole v6** - Uses session-based authentication (not compatible with v5 API keys).

## Features

- Automated scheduled backups (hourly, daily, or weekly)
- Manual backup on demand
- Backup retention policies (by count and age)
- Encrypted password storage
- Optional web UI authentication

## Generate Keys

```bash
# Generate SECRET_KEY
openssl rand -base64 48

# Generate FIELD_ENCRYPTION_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Quick Start

1. Create a `docker-compose.yml`:
   ```yaml
   services:
     pihole-checkpoint:
       image: ghcr.io/pihole-checkpoint/pihole-checkpoint:latest
       ports:
         - "8000:8000"
       volumes:
         - ./data:/app/data
         - ./backups:/app/backups
       environment:
         - SECRET_KEY=your-random-secret-key-at-least-50-chars
         - FIELD_ENCRYPTION_KEY=exactly-32-characters-here!!
         - TIME_ZONE=UTC
       restart: unless-stopped
   ```

2. Start the container:
   ```bash
   docker compose up -d
   ```

3. Open http://localhost:8000 and configure your Pi-hole connection.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `FIELD_ENCRYPTION_KEY` | Yes | Fernet key for encrypting Pi-hole passwords |
| `TIME_ZONE` | No | Scheduler timezone (default: UTC) |
| `REQUIRE_AUTH` | No | Enable web UI password protection (default: false) |
| `APP_PASSWORD` | No | Password for web UI when `REQUIRE_AUTH=true` |
| `DEBUG` | No | Enable debug mode (default: false) |
| `ALLOWED_HOSTS` | No | Comma-separated allowed hosts (default: *) |

## Data Storage

Backups and the database are stored in mounted volumes:

- `./data/` - SQLite database
- `./backups/` - Backup ZIP files

## Commands

```bash
# View logs
docker compose logs -f pihole-checkpoint

# Stop the application
docker compose down

# Rebuild after updates
docker compose up --build -d
```

## License

MIT
