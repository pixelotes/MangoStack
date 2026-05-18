# 🥭 MangoStack

A self-hosted media stack for a Raspberry Pi (ARM64), built almost entirely
from a family of small, single-purpose services I wrote myself. MangoStack is
just the glue: a `docker-compose.yaml` that wires those services together
plus a tiny homepage.

If you have ever looked at the *arr stack and thought "this is too much for
my Pi", MangoStack is the lightweight alternative I run on mine.

## What is in the stack

| Service       | Role                              | Project |
|---------------|-----------------------------------|---------|
| **Dashboarr** | Static homepage with service tiles | [pixelotes/dashboarr](https://github.com/pixelotes/dashboarr); link list lives in [`./dashboarr/services.json`](dashboarr/services.json) |
| **Tango**     | Torrent client with web UI         | [pixelotes/tango](https://github.com/pixelotes/tango) |
| **Scarf**     | Indexer proxy / aggregator         | [pixelotes/scarf](https://github.com/pixelotes/scarf) |
| **Reel**      | Movie & TV downloader/automator (also fetches subtitles) | [pixelotes/reel](https://github.com/pixelotes/reel) |
| **RMS**       | Raspberry Media Server — lightweight media server with built-in subtitle support | Docker image `pixelotes/rms:arm64` |
| **Suika**     | Manga reader                       | Docker image `pixelotes/suika:arm64` |
| Navidrome     | Music streaming                    | upstream `deluan/navidrome` |

## Repository layout

```
.
├── docker-compose.yaml   # the whole stack, with relative bind mounts
├── .env.example          # template for environment variables
├── dashboarr/            # link tiles for the homepage (services.json)
├── tango/                # Tango config + (runtime) session/data
├── reel/                 # Reel config + (runtime) data
├── rms/                  # RMS config (config.yml is tracked, rest ignored)
├── suika/                # Suika config (config.yml is tracked, rest ignored)
├── scarf/                # Scarf indexer definitions + (runtime) data
├── navidrome/            # (runtime) Navidrome state — gitignored
└── README.md
```

Configs live in the repo and are bind-mounted directly into the containers via
relative paths in `docker-compose.yaml`. Runtime state (sqlite DBs, caches,
processing-state files) ends up in the same subdirectories at runtime and is
covered by [`.gitignore`](.gitignore). Only the bulk media library
(`BASE_DIR` / `MEDIA_DIR`) lives outside the repo.

## Requirements

- A Raspberry Pi (or any ARM64 host) running Docker Engine with the
  `compose` plugin.
- A place to put media. The defaults assume a USB drive mounted at
  `/media/usb`, but any path works — adjust `.env` accordingly.

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/MangoStack.git
cd MangoStack

cp .env.example .env
$EDITOR .env                            # paths + Scarf secrets

# Fill in the credentials/API keys marked REPLACE_WITH_... in each config
$EDITOR reel/config/config.yml
$EDITOR rms/config/config.yml
$EDITOR suika/config/config.yml

# Optional: customise the homepage tiles
$EDITOR dashboarr/services.json

# Pull all images and bring the stack up
docker compose pull
docker compose up -d
```

Once running, the homepage is on <http://raspberrypi:3000> (replace
`raspberrypi` with your host name or IP).

### Generating Scarf secrets

```bash
# JWT secret
openssl rand -hex 48

# UI password — use whatever your password manager generates
```

Put both in `.env` before the first `docker compose up`.

## Per-service configuration

The shipped configs are exactly what I run on my Pi, with credentials replaced
by `REPLACE_WITH_...` placeholders. Edit them in place — there is no separate
copy step.

| Service   | Config file                              | Notes |
|-----------|------------------------------------------|-------|
| Tango     | [`tango/config.yaml`](tango/config.yaml) | tuned for Raspberry Pi 3B |
| Reel      | [`reel/config/config.yml`](reel/config/config.yml) | needs TMDB, Trakt, Scarf, OpenSubtitles keys |
| RMS       | [`rms/config/config.yml`](rms/config/config.yml)   | needs TMDB and OpenSubtitles keys |
| Suika     | [`suika/config/config.yml`](suika/config/config.yml) | just UI password + JWT |
| Scarf     | [`scarf/definitions/`](scarf/definitions) | 4 example indexer definitions; Scarf's other settings come from environment variables in `docker-compose.yaml` |
| Dashboarr | [`dashboarr/services.json`](dashboarr/services.json) | edit hostname and Trakt links |
| Navidrome | n/a — configured via env vars in `docker-compose.yaml` | |

For deeper tuning, refer to the upstream documentation:

- Tango → <https://github.com/pixelotes/tango>
- Scarf → <https://github.com/pixelotes/scarf>
- Reel  → <https://github.com/pixelotes/reel>
- RMS, Suika → see the project description on Docker Hub
- Navidrome → <https://www.navidrome.org/docs>

## License

[MIT](LICENSE).
