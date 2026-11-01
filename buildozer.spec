[app]
title = Highway Classic
package.name = highwayclassic
package.domain = org.grovekeeper
source.dir = .
source.include_exts = py,png
version = 1.0
requirements = python3,pygame
orientation = portrait
fullscreen = 1
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #1c2230
android.permissions =
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
