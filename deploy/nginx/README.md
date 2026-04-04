# Presek nginx

This nginx config is intended for `presek.live` behind Cloudflare.

Together with the files in `deploy/systemd/`, this is the supported production deployment model for the app.

## Routing model

- `https://presek.live/` goes to Astro on `127.0.0.1:3000`
- Public `/api/` requests go to Flask on `127.0.0.1:5000`
- FastAPI is kept for internal/specialized endpoints only
- Flask-only utility routes such as `/robots.txt`, `/proxy`, `sw.js`, and OG image routes stay on Flask

This keeps a single public API owner for the Astro site, which reduces route drift between Flask and FastAPI.

## Files

- `presek.live.conf`: site config for `/etc/nginx/sites-available/`
- `cloudflare-realip.conf`: snippet for `/etc/nginx/snippets/`

## Install

Copy the files to the server:

```sh
sudo cp deploy/nginx/presek.live.conf /etc/nginx/sites-available/presek.live.conf
sudo cp deploy/nginx/cloudflare-realip.conf /etc/nginx/snippets/cloudflare-realip.conf
sudo ln -s /etc/nginx/sites-available/presek.live.conf /etc/nginx/sites-enabled/presek.live.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Required edits

- Replace the `ssl_certificate` and `ssl_certificate_key` paths with your actual origin certificate paths.
- If your server user, paths, or ports differ from the systemd units, update those first.
- Keep the Cloudflare IP ranges in `cloudflare-realip.conf` current using the official Cloudflare IP lists:
  - https://www.cloudflare.com/ips-v4
  - https://www.cloudflare.com/ips-v6

## Cloudflare

- Use Cloudflare SSL mode `Full (strict)`.
- Keep nginx listening on `80/443`; the app services should stay on localhost only.
- If you firewall the origin, allow only Cloudflare IPs plus your own admin IP.
