#!/bin/sh
# Rebuild the bundled DEX after changing the monitor. End users do not need the SDK.
set -eu
src=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
sdk=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-"$HOME/Android/Sdk"}}
platform=${ANDROID_JAR:-"$sdk/platforms/android-36/android.jar"}
d8=${D8:-"$sdk/build-tools/36.0.0/d8"}
out="$src/../../.build/task-monitor"
mkdir -p "$out"/classes
javac --release 8 -cp "$platform" -d "$out/classes" \
    "$src/stubs/android/app/TaskStackListener.java" "$src/TaskMonitor.java" "$src/EmbeddedDisplay.java"
"$d8" --min-api 30 --lib "$platform" --output "$out" \
    --classpath "$out/classes" "$out/classes/org/waydroid/helper/TaskMonitor.class" \
    "$out/classes/org/waydroid/helper/EmbeddedDisplay.class"
cp "$out/classes.dex" "$src/../../waydroid_helper/controller/android/task-monitor.dex"
