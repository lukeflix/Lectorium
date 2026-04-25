[app]
title = Lectorium
package.name = lectorium
package.domain = com.lectorium.reader
source.dir = app
source.include_exts = py,png,jpg,kv,atlas,db
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True
android.gradle_dependencies =
android.enable_androidx = True
p4a.branch = master
p4a.bootstrap = sdl2
log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
