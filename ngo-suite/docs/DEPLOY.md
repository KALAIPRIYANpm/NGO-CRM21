# Putting the NGO Suite on a server

The app runs on one computer. Pick the option that fits your office.

## A. One office computer, shared on the office network (simplest)
1. Install Python 3.10 or newer on the computer that will stay switched on.
2. In the folder, run: `python run.py --host 0.0.0.0 --port 8020`
3. Staff open `http://THAT-COMPUTER-IP:8020` on the same Wi-Fi or cable network.
4. Allow port 8020 in the computer's firewall for the office network only. Do not open it to the internet.
Good for: an office where everyone works in the same place. Not good for: field staff on mobile data.

## B. A small cloud server with Docker (recommended for field staff and public pages)
1. Get a small server (1 CPU, 1 GB memory is enough) and a domain name. Point the domain's A record at the server.
2. Install Docker and Docker Compose on the server. Copy this folder to it.
3. Copy `.env.example` to `.env` and set `DOMAIN` and a long first `NGO_ADMIN_PASSWORD`.
4. Run: `docker compose up -d`
5. Open `https://YOUR-DOMAIN`. The certificate is requested and renewed automatically.
All data is in the Docker volume `ngo-data` (database, photos, backups).

## C. A Linux server without Docker
1. Copy the folder to `/opt/ngo-suite`, create a user `ngo`, and a data folder `/var/lib/ngo-suite` owned by that user.
2. Copy `deploy/ngo-suite.service` to `/etc/systemd/system/`, edit the password, then `systemctl enable --now ngo-suite`.
3. Put Caddy or nginx in front for HTTPS, forwarding to `127.0.0.1:8000`. With Caddy: `your-domain { reverse_proxy 127.0.0.1:8000 }`.

## Before real use
- Sign in, change every sample password, delete the sample users and sample data.
- Turn on two-step sign-in for administrators (Settings, Security).
- Set a public address in Settings so reply links and the Donate page work.
- Back up: download a backup from Admin, Backup and restore every week, and also copy the data folder (it holds photos).
- Updating: replace the program files and restart. Your data folder is separate and is kept.
- Only a few people should have the administrator role.

## What this does not do
It does not buy or run the server for you, set up your domain, or make the software certified for tax or audit. Ask your CA before relying on any figure.
