[app]
title = Juegos de Mesa
package.name = juegosdemesa
package.domain = org.juegos

source.dir = .
source.include_exts = py,png,jpg,ico,json
source.exclude_dirs = .git,.github,tools,bin,.buildozer,__pycache__
version = 1.0

# chess = python-chess (puro Python). pyjnius/android: red WiFi y pantalla encendida.
requirements = python3,kivy==2.3.1,python-chess,pyjnius @ git+https://github.com/kivy/pyjnius.git@1.7.0

icon.filename = %(source.dir)s/icono.png
orientation = landscape
fullscreen = 1

# Permisos: red local, ver la WiFi, recibir paquetes de descubrimiento y no dormirse.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK

# Compatibilidad máxima: Android 5.0 en adelante, celulares de 32 y 64 bits.
android.minapi = 21
android.api = 33
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.wakelock = True

[buildozer]
log_level = 2
warn_on_root = 1
