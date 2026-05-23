/* Minimal config.h stub for building arena C units outside the full
   Emscripten/autoconf environment (e.g. the smoke-test harness in CI).
   The authoritative config.h is generated at the repo root by
   `autoreconf -fi && emconfigure ./configure` — see docs/build.md. */

#ifndef DOOM_ARENA_CONFIG_H
#define DOOM_ARENA_CONFIG_H

/* Both functions are available on every platform the smoke tests run on. */
#define HAVE_DECL_STRCASECMP  1
#define HAVE_DECL_STRNCASECMP 1

#endif /* DOOM_ARENA_CONFIG_H */
