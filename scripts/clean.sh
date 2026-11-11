#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

rm -fr -- aclocal.m4 autom4te.cache autotools config.hin configure Makefile.in \
  stamp-h1 config.log config.status config.h a.wasm Makefile clean

for directory in chocolate-doom/textscreen chocolate-doom/textscreen/fonts \
  chocolate-doom/textscreen/examples chocolate-doom/opl \
  chocolate-doom/opl/examples chocolate-doom/data chocolate-doom/pcsound src src/doom; do
  (
    cd "$directory"
    rm -fr -- Makefile Makefile.in .deps ./*.o ./*.a
  )
done

for directory in chocolate-doom/textscreen/examples chocolate-doom/opl/examples; do
  (
    cd "$directory"
    rm -fr -- ./*.wasm ./*.wasm.map ./*.worker.js ./*.html ./*.html.symbols ./*.js
  )
done

rm -fr -- src/chocolate* src/org.chocolate_doom* src/Doom.desktop \
  src/Doom.metainfo.xml src/Doom_Screensaver.desktop
