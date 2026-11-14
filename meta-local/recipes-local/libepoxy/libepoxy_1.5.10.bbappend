# libepoxy o cere WPE WebKit 2.54 (navigatorul web, in imagine din 0.2.6 prin hds-navigator); altceva din imagine nu
# o foloseste. Distributia nu are "opengl" in DISTRO_FEATURES, iar EGL/GLES vin din dinobot-opengl (virtual/egl);
# libepoxy incarca libEGL.so.1 si libGLESv2.so.2 la rulare (dlopen), deci nu cere nimic din distributie.
# Numele are versiunea exacta din oe-core (1.5.10), nu %: la o versiune noua parsarea se opreste ("No recipes
# available for bbappend") si schimbarea se verifica din nou, in loc sa se aplice tacut.
REQUIRED_DISTRO_FEATURES:remove = "opengl"
# Vu+ Solo 4K, Uno 4K SE, Duo 4K (lotul vuplus4k, 06.11.2026): EGL vine din vuplus-libgles-<masina>, al carui eglplatform.h
# include X11/Xlib.h daca nu e definit BROADCOM_PLATFORM (randurile 100-120 ale fisierului din recipe-sysroot); cu el
# tipurile native sunt void *, ca la imaginile altor echipe pe Vu+. Prima constructie Solo 4K a cazut aici (06.11, 10:00).
CFLAGS:append:vusolo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuultimo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuuno4kse = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuzero4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4klite = " -DBROADCOM_PLATFORM"
# GigaBlue UHD Quad 4K Pro (ALFA): EGL din gb-v3ddriver-gb7252pro (Broadcom); macro-ul nu strica daca antetul nu-l cere
CFLAGS:append:gbquad4kpro = " -DBROADCOM_PLATFORM"
# GigaBlue UHD X3 4K (MGX): EGL din gb-v3ddriver-gb72604 (Broadcom)
CFLAGS:append:gbx34k = " -DBROADCOM_PLATFORM"
# AX HD51 (MHD): EGL din hd-v3ddriver-hd51 (Broadcom v3d-nxpl, gfutures-arm.inc)
CFLAGS:append:ax51 = " -DBROADCOM_PLATFORM"
# Edision (MED): EGL din edision-libv3d (V3D Broadcom al producatorului)
CFLAGS:append:osmio4kplus = " -DBROADCOM_PLATFORM"
CFLAGS:append:osmini4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:osmio4k = " -DBROADCOM_PLATFORM"
# Zgemma H17 COMBO (MH7): EGL din airdigital-v3ddriver-h17 (Broadcom v3d-nxpl, airdigital-arm.inc)
CFLAGS:append:zgemmah17combo = " -DBROADCOM_PLATFORM"
# Dreambox DM900 si DM920 (MDM dm900 egl): EGL din libvc5dream (Dream, Broadcom VC5); antetul nu e citit inca (arhiva
# nedescarcata), definitia e ca pe celelalte Broadcom si nu strica daca antetul nu o foloseste. Se vede la constructie.
CFLAGS:append:dm900 = " -DBROADCOM_PLATFORM"
CFLAGS:append:dm920 = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4kse = " -DBROADCOM_PLATFORM"
