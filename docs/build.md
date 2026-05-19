# Build

The WASM build needs Emscripten. Three supported paths: macOS native (Homebrew),
Linux native, or Windows via WSL. Do not use Windows `mingw32-make` for the
WASM build.

## macOS

One-time setup:

```bash
brew install automake libtool emscripten
cd src
autoreconf -fi
emconfigure ./configure
```

Then every time you change C sources:

```bash
cd src
emmake make -j4
```

For a full clean rebuild:

```bash
cd src
emmake make clean && emmake make -j4
```

This produces `src/websockets-doom.{html,js,wasm}` directly on the host (no
WSL or Docker needed for the build itself — Docker is only for serving them).

### Modern-Emscripten quirks

Recent Emscripten (~3.1+, which is what `brew install emscripten` ships) drops
some legacy globals that older Win builds relied on. The patches in
`src/index.html` already work around these:

- `Module.HEAPU8` is no longer attached by default; we fall back to the
  global `HEAPU8` for POV canvas reads
- An `Asyncify.currData` guard in the POV render loop must be removed,
  otherwise the canvases stay black because the read is always blocked
  while the Doom main loop is yielded

If you rebuild on a *much* older Emscripten (e.g., 2.x) you may not need
those fallbacks, but leaving them in is harmless.

## Linux

Same as macOS but install Emscripten via your distro or the
[emsdk](https://emscripten.org/docs/getting_started/downloads.html):

```bash
sudo apt install automake libtool
# Install emsdk separately, then:
source /path/to/emsdk_env.sh
cd src
autoreconf -fi
emconfigure ./configure
emmake make -j4
```

## Windows (WSL)

The generated Makefiles point to Linux Emscripten paths such as
`/root/emsdk/upstream/emscripten/emcc`, so run the build inside WSL:

### Rebuild Doom Library

```powershell
$wslRepo = (wsl -d Ubuntu-24.04 -e wslpath -a (Get-Location).Path).Trim()
wsl -d Ubuntu-24.04 -e bash -lc "cd '$wslRepo/src/doom' && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile libdoom.a"
```

### Rebuild Browser WASM

```powershell
$wslRepo = (wsl -d Ubuntu-24.04 -e wslpath -a (Get-Location).Path).Trim()
wsl -d Ubuntu-24.04 -e bash -lc "cd '$wslRepo/src' && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile -o doom/Makefile websockets-doom.html"
```

This rebuilds:

```text
src/websockets-doom.html
src/websockets-doom.js
src/websockets-doom.wasm
```

## Docker Runtime Assets

The v1 Docker setup is runtime-only. It does not rebuild Emscripten/WASM inside Docker; it serves the prebuilt files above.

Normal Docker runs copy `src/` into the image, so rebuilt assets require either a rebuild of the runtime image or dev mode. After rebuilding locally, run Docker in dev mode so the container serves your current `src/` working tree:

```powershell
.\scripts\start-docker.ps1 -Dev
```

```bash
bash scripts/start-docker.sh --dev
```

Then hard refresh the browser tab.

## Why WSL

The generated Makefiles point to Linux Emscripten paths such as:

```text
/root/emsdk/upstream/emscripten/emcc
```

Those paths exist inside the `Ubuntu-24.04` WSL distro, not in native Windows PowerShell.

## Browser Cache

After rebuilding, hard refresh the browser tab. Existing tabs can continue running an old WASM image until reloaded.

## Performance Build

The browser build is tuned for live duel playback: source maps, `SAFE_HEAP`, and `STACK_OVERFLOW_CHECK` are disabled in the generated Emscripten flags to avoid avoidable FPS overhead. Re-enable those checks only for a focused debugging build, then rebuild and hard refresh the browser tab.

## Common Failure

Plain `make` can try to refresh Autotools files and fail with:

```text
config.status: error: invalid argument: src/doom/Makefile
```

Use the documented `-o Makefile` commands above.
