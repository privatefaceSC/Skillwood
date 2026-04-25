#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d android ]; then
    echo "Папки android/ нет — что-то не так." >&2
    exit 1
fi

cd android
./gradlew assembleDebug --no-daemon

mkdir -p ../dist
cp app/build/outputs/apk/debug/app-debug.apk ../dist/skillwood.apk

echo "Готово: dist/skillwood.apk ($(du -h ../dist/skillwood.apk | cut -f1))"
