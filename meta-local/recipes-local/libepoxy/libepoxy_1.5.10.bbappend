# libepoxy o cere WPE WebKit 2.54 (navigatorul web, in imagine din 0.2.6 prin hds-navigator); altceva din imagine nu
# o foloseste. Distributia nu are "opengl" in DISTRO_FEATURES, iar EGL/GLES vin din dinobot-opengl (virtual/egl);
# libepoxy incarca libEGL.so.1 si libGLESv2.so.2 la rulare (dlopen), deci nu cere nimic din distributie.
# Numele are versiunea exacta din oe-core (1.5.10), nu %: la o versiune noua parsarea se opreste ("No recipes
# available for bbappend") si schimbarea se verifica din nou, in loc sa se aplice tacut.
REQUIRED_DISTRO_FEATURES:remove = "opengl"
