# Deploying the Ledgerline API on EC2 (no Docker)

This deploys the FastAPI backend to a single Ubuntu EC2 instance. Nginx handles HTTPS and proxying, systemd keeps the API running, and a Python virtualenv holds pinned, hash-checked dependencies. The frontend can stay on Vercel (or any static host) and call this API.

```text
Browser ──HTTPS──> Nginx :443 ──> Uvicorn 127.0.0.1:8000 (systemd: ledgerline-api)
                                      ├── FastAPI routes
                                      └── 3 extraction worker threads ──> OpenAI
                                  Postgres (DB_URL)        /var/lib/ledgerline/storage
```

On EC2 the API runs as a normal long-lived process. Unlike on Vercel:

- extraction runs in real background workers
- uploads can be up to 15 MB
- there is no request time limit
- bills left in progress by a restart are re-queued automatically

## Files

| File | Installed to | Purpose |
|------|--------------|---------|
| `setup.sh` | | One-time server setup (safe to re-run) |
| `deploy.sh` | | Deploy the latest code, with automatic rollback |
| `common.sh` | | Paths and helpers shared by both scripts |
| `ledgerline-api.service` | `/etc/systemd/system/` | systemd unit: user, environment, restart policy, hardening |
| `nginx-ledgerline-api.conf` | `/etc/nginx/sites-available/ledgerline-api` | Reverse proxy, upload size, timeouts, request IDs |
| `ledgerline.env.example` | `/etc/ledgerline/ledgerline.env` | Production settings (secrets live only on the server) |
| `../../backend/requirements.lock` | | Exact dependency versions with SHA-256 hashes |

Layout on the server:

| Path | Owner | Contents |
|------|-------|----------|
| `/opt/ledgerline` | `ledgerline` | Git checkout. Read-only to the running service. |
| `/opt/ledgerline/backend/.venv` | `ledgerline` | Python virtualenv |
| `/etc/ledgerline/ledgerline.env` | `root:ledgerline`, mode 640 | Settings and secrets |
| `/var/lib/ledgerline/storage` | `ledgerline` | Uploaded documents (the only writable path) |

## 1. Launch the instance

- **AMI:** Ubuntu Server 24.04 LTS (x86_64 or ARM/Graviton; both work).
- **Type:** `t3.small` (2 GB RAM) is enough for the MVP. Use `t3.medium` for heavy scanning.
- **Region:** the same region as your database (for example `ap-south-1` Mumbai) to keep latency low.
- **Storage:** 20 GB gp3.
- **Security group inbound rules:**
  - SSH (22) from **your IP only**
  - HTTP (80) from anywhere
  - HTTPS (443) from anywhere
- **Elastic IP:** attach one so the address survives stop and start.
- **Domain (recommended):** create a DNS `A` record such as `api.yourdomain.com` pointing to the Elastic IP.
- **Database:** if Postgres runs on another machine, allow port 5432 from this instance's IP (or its security group).

## 2. Run setup

```bash
ssh -i your-key.pem ubuntu@<elastic-ip>

git clone https://github.com/Subhashbisnoi/wisprflow.git
cd wisprflow

# With a domain (gets a free Let's Encrypt certificate and redirects HTTP to HTTPS):
sudo ./deploy/ec2/setup.sh --domain api.yourdomain.com --email you@yourdomain.com

# Without a domain (plain HTTP on the IP; fine for testing only):
sudo ./deploy/ec2/setup.sh
```

The first run installs packages, creates the `ledgerline` system user, clones the code into `/opt/ledgerline`, and writes `/etc/ledgerline/ledgerline.env` with a freshly generated `JWT_SECRET`. It then stops and asks you to fill in your settings:

```bash
sudo nano /etc/ledgerline/ledgerline.env
# Set DB_URL, OPENAI_API_KEY and CORS_ORIGINS (your frontend's URL)
```

Run the **same setup command again**. This time it:

1. installs the pinned dependencies into the virtualenv
2. runs the database migrations
3. installs and starts the `ledgerline-api` systemd service and waits for its health check
4. configures Nginx and (with `--domain` and `--email`) obtains the HTTPS certificate

Check it:

```bash
curl https://api.yourdomain.com/api/v1/health      # {"status":"ok"}
```

Interactive API docs are at `https://api.yourdomain.com/docs`.

## 3. Connect the frontend

Point the web app at the API and allow its origin:

1. On the frontend host (for example the Vercel project `wisprflow`), set `VITE_API_BASE_URL=https://api.yourdomain.com/api/v1` and `VITE_MAX_UPLOAD_MB=15`, then redeploy.
2. On the server, make sure `CORS_ORIGINS` in `/etc/ledgerline/ledgerline.env` contains the frontend URL (for example `https://wisprflow-eta.vercel.app`), then run `sudo systemctl restart ledgerline-api`.

> **HTTPS is required when the frontend is served over HTTPS.** Browsers block an `https://` page from calling an `http://` API (mixed content). Use a domain with the certificate step above. Without a domain you can still try it by adding a rewrite to `frontend/vercel.json` that forwards `/api/:path*` to `http://<elastic-ip>/api/:path*`, but that sends traffic between Vercel and the server unencrypted.

## 4. Deploy updates

After merging to `main`:

```bash
ssh -i your-key.pem ubuntu@<elastic-ip>
sudo /opt/ledgerline/deploy/ec2/deploy.sh                # latest main
sudo /opt/ledgerline/deploy/ec2/deploy.sh --ref v0.2.0   # a specific tag or commit
```

`deploy.sh` does the following:

1. fetches the code
2. installs the pinned dependencies
3. runs migrations
4. restarts the service
5. waits for the health check

**If the new version is unhealthy, it automatically rolls the code back to the previous commit and restarts.** Database migrations are not rolled back. Ledgerline's migrations only add tables and columns, so the previous code keeps working against a newer schema.

## 5. Operate

| Task | Command |
|------|---------|
| Live API logs (JSON, one line per event) | `sudo journalctl -u ledgerline-api -f` |
| Errors only | `sudo journalctl -u ledgerline-api -p warning --since "1 hour ago"` |
| Find a request by the ID the user reports | `sudo journalctl -u ledgerline-api \| grep <request_id>` |
| Nginx access log (includes the same request ID) | `sudo tail -f /var/log/nginx/ledgerline-api.access.log` |
| Status / restart | `sudo systemctl status ledgerline-api` / `sudo systemctl restart ledgerline-api` |
| Change a setting | Edit `/etc/ledgerline/ledgerline.env`, then restart the service |
| Load demo data | See the last lines printed by `setup.sh` |
| Renew HTTPS | Automatic (`certbot.timer`). Test with `sudo certbot renew --dry-run`. |

**Backups:**

- **Database:** use your Postgres backups.
- **Documents:** snapshot the EBS volume (AWS Data Lifecycle Manager can automate daily snapshots). Alternatively, set `STORAGE_BACKEND=database` so documents live in Postgres and one backup covers everything.

## 6. Security notes

- The API listens on `127.0.0.1:8000` only. The internet reaches it through Nginx.
- The service runs as an unprivileged `ledgerline` user with systemd hardening. The code is read-only to it, and only `/var/lib/ledgerline` is writable.
- Secrets live only in `/etc/ledgerline/ledgerline.env` (mode 640). They are never in the repository or the process command line.
- Dependencies are installed with `--require-hashes`, so a tampered package fails to install.
- Keep SSH (port 22) restricted to your IP, or use AWS Systems Manager Session Manager and close port 22 entirely.
- Install security updates automatically: `sudo apt install unattended-upgrades` (enabled by default on Ubuntu 24.04).

## 7. Scaling later

The service runs **one Uvicorn process** on purpose: the background job queue lives inside it, and pending work is recovered on startup. To grow:

1. **Scale up:** a bigger instance, plus a higher `EXTRACTION_WORKERS` (AI calls spend most of their time waiting, so threads scale well).
2. **Scale out:** move the job queue to Redis with separate worker processes, run several API instances behind an Application Load Balancer, and set `STORAGE_BACKEND=database` or add S3 storage so every instance sees the same documents. See [technical architecture section 8](../../docs/04-technical-architecture.md#8-scaling-horizontally).
