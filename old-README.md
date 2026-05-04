# Wasm Doom

This is a [Chocolate Doom][1] WebAssembly port with WebSockets [support][4].

## Requirements

You need to install Emscripten and a few other tools first:

```
brew install emscripten
brew install automake
brew install sdl2 sdl2_mixer sdl2_net
```

## Compiling

There are two scripts to facilitate compiling Wasm Doom:

```
./scripts/clean.sh
./scripts/build.sh
```

## Running

Copy the shareware version of [doom1.wad][3] to [./src][9] (make sure it has the name doom1.wad)

Then:

```
cd src
python -m SimpleHTTPServer
```

Then open your browser and point it to http://0.0.0.0:8000/

Doom should start (local mode, no network). Check [doom-workers][8] if you want to run multiplayer locally.

Inspect [src/index.html][6] for startup details.

Check our live multiplayer [demo][5] and [blog post][7].

## Rootly Incident Mode

This fork can run E1M8 as a Rootly incident visualization arena. Doom never receives a Rootly token. The browser only loads a local TSV file.

Mock mode works without Rootly:

```powershell
cd src
py -m http.server 8000
```

Open:

```text
http://127.0.0.1:8000/?incidentData=mock
```

Live local TSV mode:

```powershell
$env:ROOTLY_API_TOKEN="your-rootly-token"
py scripts\rootly_dev_server.py --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Click `Load Last Week`. The browser calls the local `/api/rootly/last-week` endpoint. That local Python server reads `ROOTLY_API_TOKEN`, calls Rootly, writes `src/rootly_incidents.local.tsv`, then Doom loads the TSV. The token is never written to disk, included in WASM, or sent to the browser.

Manual live TSV generation still works:

```powershell
$env:ROOTLY_API_TOKEN="your-rootly-token"
py scripts\fetch_rootly_incidents.py
cd src
py -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000/?incidentData=local
```

Default mode auto-selects `src/rootly_incidents.local.tsv` when it exists and falls back to `src/rootly_incidents.mock.tsv` otherwise:

```text
http://127.0.0.1:8000/
```

The generated live TSV is `src/rootly_incidents.local.tsv`; it is gitignored because incident titles and links may be sensitive. The checked-in `src/rootly_incidents.mock.tsv` remains safe for demos. An empty TSV with only the header is valid and produces a clean E1M8 arena with no incident monsters.

Useful ingest options:

```powershell
py scripts\fetch_rootly_incidents.py --lookback-days 7 --time-field created_at --max-incidents 24 --output src/rootly_incidents.local.tsv
```

### Screenshots / GIF

Placeholder: add a screenshot or short GIF here showing the E1M1 Rootly arena with severity-labeled monsters.

## stdout procotol

To show important messages coming from the game while it's running we send the following formatted stdout messages, which can be parsed in the web page running the wasm:

```
doom: 1, failed to connect to websockets server
doom: 2, connected to %s
doom: 3, we're out of client addresses
doom: 4, ws error(eventType=%d, userData=%d)
doom: 5, ws close(eventType=%d, wasClean=%d, code=%d, reason=%s, userData=%d)
doom: 6, failed to send ws packet, reconnecting
doom: 7, failed to connect to %s
doom: 8, uid is %d
doom: 9, disconnected from server
doom: 10, game started
doom: 11, entering fullscreen
doom: 12, client '%s' timed out and disconnected
```

## License

Chocolate Doom and this port are distributed under the GNU GPL. See the COPYING file for more information.

[1]: https://github.com/chocolate-doom/chocolate-doom
[2]: https://emscripten.org/
[3]: https://doomwiki.org/wiki/DOOM1.WAD
[4]: src/net_websockets.c
[5]: https://silentspacemarine.com
[6]: src/index.html
[7]: https://blog.cloudflare.com/doom-multiplayer-workers
[8]: https://github.com/cloudflare/doom-workers
[9]: src
