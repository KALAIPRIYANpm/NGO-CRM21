# Using NGO Suite over the internet (HTTPS)

The software listens on this computer only (`127.0.0.1`). That is the safe default.
Staff in the field need to reach it from their phones, so put a secure front door in front of it.
**Never open the port directly on your router.** The app itself speaks plain HTTP; HTTPS is added by the front door.

Without HTTPS, passwords and photos travel readable across the network, and phone cameras and the
installable app will not work from a normal web address. (They do work on `http://127.0.0.1` on the same computer.)

## Option A: Cloudflare Tunnel (free, no router changes, recommended)

1. Create a free Cloudflare account and add a domain you own (a cheap `.in` or `.org` domain is fine).
2. Install `cloudflared` on the computer that runs NGO Suite and sign in: `cloudflared tunnel login`
3. `cloudflared tunnel create ngo` then `cloudflared tunnel route dns ngo app.yourngo.org`
4. Create `config.yml` next to the tunnel file:
   ```
   tunnel: ngo
   credentials-file: /path/to/ngo.json
   ingress:
     - hostname: app.yourngo.org
       service: http://127.0.0.1:8020
     - service: http_status:404
   ```
5. `cloudflared tunnel run ngo` (install it as a service so it starts with the computer).
6. Open `https://app.yourngo.org` on a phone, sign in, and use the browser's "Install app" / "Add to Home Screen".

## Option B: Caddy on a server with a public address

```
app.yourngo.org {
    reverse_proxy 127.0.0.1:8020
}
```
Caddy gets and renews the certificate by itself.

## What the software does once it sits behind HTTPS

- It trusts the `X-Forwarded-Proto` and client-address headers **only** when the connection comes from the same computer (the tunnel or Caddy), so nobody on the internet can fake them.
- Cookies get the `Secure` flag and the browser is told to insist on HTTPS (`Strict-Transport-Security`).
- The sign-in rate limit counts each person's real address instead of the proxy's.
- If your setup does not send `X-Forwarded-Proto`, set the environment variable `NGO_FORCE_SECURE=1` before starting.

## Checklist before real use

- [ ] Change every demo password (Admin, Users). Delete demo users you do not need.
- [ ] Admin, Settings, Security: set **Require two-step sign-in for administrators** to Yes, then set it up for yourself.
- [ ] Turn on two-step sign-in for finance users too (the Security button, top right).
- [ ] Keep `data/secret.key` **separate** from backups (see README, Security).
- [ ] Keep the computer's operating system updated and use a screen lock.
