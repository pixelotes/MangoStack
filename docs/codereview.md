# MangoStack Code Review and Architecture Documentation

## 1. Overview
MangoStack is a collection of eight highly specialized, lightweight services designed to function as a cohesive, self-hosted media ecosystem. Its primary goal is to provide all the functionality of large, resource-intensive media management suites (like Sonarr/Radarr/Plex) while maintaining an exceptionally small memory footprint suitable for low-power devices, notably the Raspberry Pi.

The project is built around the principle of modularity and efficiency, utilizing Docker to isolate each service and manage resource consumption.

## 2. Architecture
MangoStack employs a **Microservices Architecture** orchestrated entirely via `docker-compose.yaml`.

*   **Isolation:** Each service runs in its own Docker container, ensuring that resource spikes in one component (e.g., a heavy indexer query in `Scarf`) do not destabilize the entire stack.
*   **Resource Management:** The `docker-compose.yaml` explicitly defines `deploy` resource limits for almost every service, aggressively controlling CPU and Memory usage to maximize efficiency on ARM64 hardware.
*   **Configuration:** Configuration is externalized. Services are designed to read configuration files (`.yml` or `services.json`) that are mounted directly from the host machine into the respective container volumes.
*   **Networking:** Services communicate implicitly over the internal Docker network defined by the compose file, accessing shared media directories mounted from the host via `BASE_DIR`/`MEDIA_DIR`.

## 3. Component Breakdown

### A. Orchestration & Interface
*   **`dashboarr`**: The entry point of the stack. It is a lightweight static homepage that provides visual links (tiles) to all running services, offering a unified user interface for the ecosystem.
*   **`docker-compose.yaml`**: The master orchestrator. It defines dependencies, ports, volumes, and resource limits, acting as the glue that wires all specialized services together.

### B. Media Discovery & Acquisition
*   **`scarf` (Indexer Proxy / Aggregator)**: Acts as the single point of contact for media sources. It proxies requests to various indexers (e.g., YTS, The Pirate Bay) and aggregates search results into a unified, fast API.
*   **`tango` (Download Client UI)**: A minimal web UI wrapper around `aria2c`. It provides the interface for initiating downloads, utilizing the robust functionality of `aria2c`.

### C. Media Processing & Management
*   **`reel` (Media & TV Automator)**: This is the core logic engine. It bridges the gap between discovery and storage. `Reel` is responsible for:
    *   Taking search results from `Scarf`.
    *   Initiating downloads via `Tango`.
    *   Running post-processing tasks (renaming, fetching metadata, adding posters, subtitles) once downloads are complete.

### D. Serving Services (The "Readers")
These services provide the end-user interface for the stored media:
*   **`rms` (Raspberry Media Server)**: The primary media server. It functions similarly to Jellyfin or Emby, providing a media library view and streaming capabilities with integrated subtitle support.
*   **`kaze` (Music Server)**: A minimal, Subsonic-compatible music server that serves music directly from the filesystem without relying on a database for maximum speed and simplicity.
*   **`suika` (Manga Reader)**: A dedicated reader for manga files, offering a streamlined browsing experience.
*   **`sumi` (Ebook Reader)**: A dedicated, minimal reader for EPUB files, designed for low-resource environments.

## 4. Data Flow and Interaction
The services operate in a linear, functional pipeline:

1.  **User Request:** The user interacts with `dashboarr` to navigate to a service or uses `Scarf` to search.
2.  **Discovery:** The request hits `Scarf`, which queries configured external indexers.
3.  **Download Initiation:** `Reel` receives the desired media/show information from `Scarf` and instructs `Tango` to begin the download process for the specified file.
4.  **Processing:** Once `Tango` completes the download, `Reel` takes over. It uses external APIs (TMDB, Trakt, etc.) to enrich the file with metadata and applies defined rules (renaming, moving, generating posters).
5.  **Serving:** The finalized media files are placed in the shared `MEDIA_DIR`. The serving services (`RMS`, `Kaze`, `Suika`, `Sumi`) read these finalized files and expose them via their respective ports for client consumption.

## 5. Key Design Principles
*   **Lightweight Focus:** Every component is explicitly designed to be minimal, avoiding heavy databases or complex internal state management where possible (e.g., `Kaze` and `Sumi` are filesystem-first).
*   **Decoupling:** The services are loosely coupled. As noted in the documentation, `Reel` does not care if the download client is `Tango` or any other standard client; it only requires a standardized API interaction. Similarly, `Reel` can use a different indexer aggregator than `Scarf`.
*   **Extensibility:** The architecture supports "Mix and Match." Users can easily remove components (e.g., `Kaze` if they only stream music) by commenting out their service blocks in `docker-compose.yaml` without breaking the remaining stack.
*   **Security Posture:** The design assumes a **Trusted Local Area Network (LAN)**. The services are not intended for direct public exposure and lack hardened security features, relying instead on local network trust.

## 6. Summary
MangoStack is a highly efficient, well-architectured solution for self-hosting a media stack on limited hardware. By leveraging Docker to isolate small, purpose-built services, it achieves a significantly lower resource overhead compared to monolithic, off-the-shelf solutions. The clear separation of concerns between discovery (`Scarf`), acquisition (`Tango`/`Reel`), and serving (`RMS`/etc.) results in a robust and maintainable system.