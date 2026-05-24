/* Minimal config.h stub for building arena C units outside the full
   Emscripten/autoconf environment (e.g. the smoke-test harness in CI).
   The authoritative config.h is generated at the repo root by
   `autoreconf -fi && emconfigure ./configure` — see docs/build.md. */

#ifndef DOOM_ARENA_CONFIG_H
#define DOOM_ARENA_CONFIG_H

/* Both functions are available on every platform the smoke tests run on. */
#define HAVE_DECL_STRCASECMP  1
#define HAVE_DECL_STRNCASECMP 1

/* Package metadata used by the browser build when this stub shadows root config.h. */
#define PACKAGE "doom-ws-wasm"
#define PACKAGE_BUGREPORT "celso@cloudflare.com"
#define PACKAGE_NAME "Websockets Doom"
#define PACKAGE_STRING "Websockets Doom 0.0.1"
#define PACKAGE_TARNAME "doom-ws-wasm"
#define PACKAGE_URL ""
#define PACKAGE_VERSION "0.0.1"
#define PROGRAM_PREFIX "websockets-"
#define VERSION "0.0.1"

#endif /* DOOM_ARENA_CONFIG_H */
