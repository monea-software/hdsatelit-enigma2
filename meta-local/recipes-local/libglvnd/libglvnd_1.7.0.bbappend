# NAV9 (0.8.0, 26.11.2026; Eduard 22:02: „orice imagine are si navigator webkit inclus”): ZGEMMA H8.2H Plus (masina h8,
# HiSilicon 3716mv430) nu are nicio biblioteca EGL/GLES de la producator (h8.conf: HAVE_GLES = "", no-opengl; in
# meta-airdigital nu exista reteta Mali pentru 3716mv430), deci wpewebkit cadea la citire: „Nothing PROVIDES virtual/libgles2”
# (NAV8). Pe h8 libglvnd da anteturile Khronos, egl.pc/glesv2.pc si libEGL.so.1/libGLESv2.so.2 fara niciun furnizor
# (eglGetDisplay intoarce EGL_NO_DISPLAY, nu cade). Desenul navigatorului e oricum pe procesor (wpewebkit 0004/0006,
# lansatorul incearca EGL prin dlopen si trece singur pe procesor), iar libWPEWebKit nu e legat de libEGL (Depends din
# pachetul mips32el si cortexa15hf: fara libEGL; numai libepoxy, care il incarca la nevoie). eglplatform.h din libglvnd da
# tipuri void * pe __unix__ fara USE_X11, deci nu trebuie BROADCOM_PLATFORM / EGL_NO_X11.
# Totul numai :h8: pe celelalte masini reteta ramane sarita (REQUIRED_DISTRO_FEATURES opengl glvnd) si semnaturile nu se schimba.
# Numele are versiunea exacta din oe-core: la o versiune noua citirea se opreste si se verifica din nou.
REQUIRED_DISTRO_FEATURES:remove:h8 = "opengl glvnd"
PACKAGECONFIG:h8 = "egl gles2"
# PACKAGECONFIG[egl] recomanda virtual-libegl-icd (un furnizor adevarat); pe h8 nu exista si nu trebuie
RRECOMMENDS:${PN}:remove:h8 = "virtual-libegl-icd"
# Lantul 0.8.0 (27.11 00:49): wpewebkit cere la rulare virtual-egl si virtual-libgles2; pe h8 nu le dadea nimeni
# („Nothing RPROVIDES 'virtual-egl'”), deci hds-navigator si toata imaginea erau „unbuildable”. libglvnd le da aici.
RPROVIDES:${PN}:append:h8 = " virtual-egl virtual-libgles2"
# NAV9d (27.11 05:27): PACKAGECONFIG[egl] din oe-core are RDEPENDS virtual-libegl-icd (al patrulea camp, nu RRECOMMENDS), deci
# RRECOMMENDS:remove de mai sus nu ajungea: „Nothing RPROVIDES 'virtual-libegl-icd'”. Pe h8 nu exista furnizor, se scoate.
# Reteta e sarita pe celelalte masini (REQUIRED_DISTRO_FEATURES), deci schimbarea nu atinge alte semnaturi.
PACKAGECONFIG[egl] = "-Degl=true,-Degl=false,,"
