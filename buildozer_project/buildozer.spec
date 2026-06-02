[app]
title = איילון פוליסות
package.name = ayalon_policies
package.domain = org.personal.ayalon

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy,requests,beautifulsoup4,android,pyjnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, READ_SMS, RECEIVE_SMS
android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

android.arch = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
