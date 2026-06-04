# VM deploy notes

One-time setup on the Ubuntu VM:

```bash
# 1. Clone repo
cd ~
git clone <your-repo-url> movie_tracker
cd movie_tracker/server

# 2. Install pipenv + deps
sudo apt install -y pipenv
pipenv install --deploy

# 3. Create .env (server reads these)
cat > .env <<'EOF'
SECRET_KEY=<random string, e.g. `openssl rand -hex 32`>
JWT_SECRET_KEY=<random string>
OMDB_API_KEY=<from omdbapi.com>
# Optional — leave blank to use SQLite
DATABASE_URL=
# Optional — only needed if you re-enable streaming
WATCHMODE_API_KEY=
EOF
chmod 600 .env

# 4. First migration
pipenv run flask db upgrade

# 5. Find the pipenv venv path — you'll paste it into the systemd unit
pipenv --venv

# 6. Install the systemd unit
#    - Edit deploy/cuedup-api.service: replace REPLACE_WITH_VM_USER (e.g. 'blake')
#      and REPLACE_WITH_PIPENV_VENV_PATH (from step 5)
sudo cp ../deploy/cuedup-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cuedup-api
sudo systemctl start cuedup-api
sudo systemctl status cuedup-api

# 7. Point your existing Cloudflare Tunnel at it
#    Add an ingress rule in ~/.cloudflared/config.yml (or via dashboard):
#      - hostname: cuedup-api.yourdomain.com
#        service: http://localhost:5555
#    Then: sudo systemctl restart cloudflared
```

After that, every future deploy is just:

```bash
~/movie_tracker/deploy/deploy.sh
```

Tail logs with:

```bash
journalctl -u cuedup-api -f
```

Don't forget to flip `USE_LOCAL_BACKEND = false` and update the URL in
[`src/config.ts`](../../CuedUp/src/config.ts) on the mobile side.
