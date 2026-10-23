# Copiat din openembedded-core (ramane sub licenta MIT a stratului openembedded-core): glib fara pachete, pentru
# pornirea lui gobject-introspection, la aceeasi versiune ca glib-2.0 (2.88.4, ca in openembedded-core);
# glib.inc din acest dosar.
require glib.inc
PACKAGES = ""
PACKAGECONFIG = ""

inherit nopackages
