# Presek deploy

If you do not want to install the nginx and systemd files manually, use:

```sh
sudo bash deploy/install_server.sh
```

You can override defaults with environment variables:

```sh
sudo DOMAIN=presek.live \
  SERVER_USER=emiloffingen \
  APP_ROOT=/home/emiloffingen/presek \
  CERT_FULLCHAIN=/etc/ssl/cloudflare/presek.live/fullchain.pem \
  CERT_PRIVKEY=/etc/ssl/cloudflare/presek.live/privkey.pem \
  bash deploy/install_server.sh
```

Before running it on the server, make sure:

- nginx is installed
- the Python virtualenv exists at the app root
- `web/dist/server/entry.mjs` exists
- your Cloudflare origin certificate files are already on disk
