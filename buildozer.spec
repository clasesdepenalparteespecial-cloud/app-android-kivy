[app]

# (OBLIGATORIO) Título de tu aplicación
title = Subir clases

# (OBLIGATORIO) Nombre del paquete (sin espacios ni guiones)
package.name = miapp

# (OBLIGATORIO) Dominio del paquete (puede ser inventado)
package.domain = org.test

# (OBLIGATORIO) Archivo principal de tu aplicación
source.dir = .

# Archivos a incluir (py para python, json para tus configs, etc.)
source.include_exts = py,png,jpg,kv,atlas,json

# (MUY IMPORTANTE) Patrones para incluir carpetas completas.
# Esto asegura que tu carpeta 'tokens' se empaquete en la app.
source.include_patterns = tokens/*, assets/*

# Versión de tu aplicación
version = 0.1

# (OBLIGATORIO) Lista de dependencias de tu app.
# Estas son las librerías que se instalarán.
requirements = python3,kivy,plyer,google-api-python-client,google-auth-oauthlib,google-auth-httplib2,requests

# Orientación de la pantalla (puedes elegir entre 'portrait', 'landscape' o ambas)
orientation = portrait

# Icono de la aplicación
# icon.filename = %(source.dir)s/icon.png

# Pantalla de carga (splash)
# presplash.filename = %(source.dir)s/presplash.png

# Permite que la app se mueva a la tarjeta SD
android.allow_backup = True

# Permisos que necesitará tu aplicación en Android.
# INTERNET para la subida, STORAGE para leer los archivos a subir.
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Requisitos de Android
# API nivel 31 es un buen estándar actual
android.api = 31
# Mínimo API 21 (Android 5.0) para amplia compatibilidad
android.minapi = 21

[buildozer]

# Nivel de detalle de los mensajes en la terminal (2 es muy detallado, útil para errores)
log_level = 2

# Número de advertencias a mostrar (0 = sin límite)
warn_count = 0