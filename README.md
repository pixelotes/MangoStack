# 🥭 MangoStack

A self-hosted media stack for a Raspberry Pi (ARM64), built almost entirely
from a family of small, single-purpose services I wrote myself. MangoStack is
just the glue: a `docker-compose.yaml` that wires those services together,
plus a tiny homepage and a maintenance script.

If you have ever looked at the *arr stack and thought "this is too much for
my Pi", MangoStack is the lightweight alternative I run on mine.

## What is in the stack

| Service       | Role                              | Project |
|---------------|-----------------------------------|---------|
| **Dashboarr** | Static homepage with service tiles | [pixelotes/dashboarr](https://github.com/pixelotes/dashboarr) (built locally from [`./dashboarr`](dashboarr)) |
| **Tango**     | Torrent client with web UI         | [pixelotes/tango](https://github.com/pixelotes/tango) |
| **Scarf**     | Indexer proxy / aggregator         | [pixelotes/scarf](https://github.com/pixelotes/scarf) |
| **Reel**      | Movie & TV downloader/automator    | [pixelotes/reel](https://github.com/pixelotes/reel) |
| **RMS**       | Raspberry Media Server (lightweight Jellyfin-like) | Docker image `pixelotes/rms:arm64` |
| **Suika**     | Manga reader                       | Docker image `pixelotes/suika:arm64` |
| **Subtitlarr** *(optional)* | Subtitle downloader for an existing library | [pixelotes/subtitlarr](https://github.com/pixelotes/subtitlarr) |
| **Janitorr**  | One-shot Python script that prunes lower-quality duplicates from the library | [`./janitorr`](janitorr) (mirror of [pixelotes/janitorr](https://github.com/pixelotes/janitorr)) |
| Jellyfin      | Drop-in alternative to RMS         | upstream `lscr.io/linuxserver/jellyfin` |
| Navidrome     | Music streaming                    | upstream `deluan/navidrome` |

Subtitlarr is not part of the default `docker-compose.yaml` but slots in
cleanly if you want it — see its README for the service block.

> Note on the media server: both **Jellyfin** and **RMS** are declared in the
> compose file and both publish on host port `8096`. Pick the one you want and
> either remove the other or change its port mapping before `docker compose up`.

## Repository layout

```
.
├── docker-compose.yaml   # the whole stack
├── .env.example          # template for environment variables
├── dashboarr/            # static homepage (Dockerfile, html, services.json)
├── janitorr/             # standalone maintenance script
└── README.md
```

Per-service runtime state (databases, caches, downloaded media) lives outside
the repository, under whatever you set as `CONFIG_DIR`, `BASE_DIR` and
`MEDIA_DIR`. The repo only carries declarative configuration.

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
$EDITOR .env                 # set PUID/PGID/TZ and paths, generate secrets

# Optional: customise the homepage links
$EDITOR dashboarr/services.json

# Pull all images and build the Dashboarr container
docker compose pull
docker compose build

# Bring the stack up
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

Most services read their config from `${CONFIG_DIR}/<service>/...`. On first
start each container will create its own defaults; from there, follow the
upstream project's documentation:

- Tango → <https://github.com/pixelotes/tango>
- Scarf → <https://github.com/pixelotes/scarf>
- Reel  → <https://github.com/pixelotes/reel>
- RMS, Suika → see the project description on Docker Hub
- Jellyfin → <https://jellyfin.org/docs>
- Navidrome → <https://www.navidrome.org/docs>

## Janitorr

[`janitorr/janitorr.py`](janitorr/janitorr.py) is a standalone Python
script (no container) that scans a media library, finds duplicate
movies/episodes and keeps the highest-quality copy of each. Run it with
`python3 janitorr/janitorr.py --help` for the full set of flags.

## License

[MIT](LICENSE).
