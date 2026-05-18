# Build

Use WSL with the Emscripten SDK. Do not use Windows `mingw32-make` for the WASM build.

## Rebuild Doom Library

```powershell
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/c/Users/muhha/OneDrive/Desktop/doom-wasm/src/doom && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile libdoom.a"
```

## Rebuild Browser WASM

```powershell
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/c/Users/muhha/OneDrive/Desktop/doom-wasm/src && source /root/emsdk/emsdk_env.sh >/dev/null && make -f Makefile -o Makefile -o doom/Makefile websockets-doom.html"
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
