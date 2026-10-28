# Modificat de moneasoftware.com si hdsatelit.com, 2026
AC_INIT([enigma2],[0.6.9],[https://hdsatelit.com])
AM_INIT_AUTOMAKE([dist-bzip2 no-define tar-pax -Wno-portability])
AC_CONFIG_HEADERS([enigma2_config.h])

# Silent rules are available since 1.11, but older versions
# are still in use. So don't use them unconditionally.
m4_ifdef([AM_SILENT_RULES], [AM_SILENT_RULES([yes])])

AC_USE_SYSTEM_EXTENSIONS
AC_SYS_LARGEFILE

AC_PROG_CC
AC_PROG_CXX
MM_AX_CXX_COMPILE_STDCXX([17], [noext], [mandatory])
m4_ifdef([LT_INIT], [LT_INIT], [AC_PROG_LIBTOOL])
AC_CONFIG_MACRO_DIR([m4])

AC_CHECK_HEADERS([dbox/fp.h dbox/lcd-ks0713.h])

AC_PATH_PROG(MSGFMT, msgfmt, AC_MSG_ERROR(Could not find msgfmt))

AM_PATH_PYTHON([3.11])
PKG_CHECK_MODULES(PYTHON, [python-$PYTHON_VERSION-embed], [], [PKG_CHECK_MODULES(PYTHON, [python3-embed])])
PYTHON_CPPFLAGS="$PYTHON_CFLAGS"
PYTHON_LDFLAGS="$PYTHON_LIBS"
AC_SUBST(PYTHON_CPPFLAGS)
AC_SUBST(PYTHON_LDFLAGS)
AX_PKG_SWIG([4.0.0], [], [AC_MSG_ERROR([SWIG 4 or newer is required])])
SWIG_PYTHON_OPT="-python"
AC_SUBST(SWIG_PYTHON_OPT)
AX_PTHREAD

TUXBOX_APPS_DVB

AM_CONDITIONAL(HAVE_GIT_DIR, test -d "$srcdir/.git")
AM_CONDITIONAL(HAVE_FAKE_GIT_DIR, test -f "$srcdir/.git/last_commit_info")

PKG_CHECK_MODULES(BASE, [freetype2 fribidi libdvbsi++ libpng libxml-2.0 sigc++-3.0])

AC_ARG_WITH(gstreamer,
	AS_HELP_STRING([--with-gstreamer],[media playback with GStreamer 1.0, yes or no]),
	[with_gstreamer=$withval],[with_gstreamer=no])
if test "$with_gstreamer" = "yes"; then
	PKG_CHECK_MODULES(GSTREAMER, [gstreamer-1.0 gstreamer-pbutils-1.0])
	AC_DEFINE([HAVE_GSTREAMER],[1],[Define to 1 to build GStreamer media playback])
fi
AM_CONDITIONAL(HAVE_GSTREAMER, test "$with_gstreamer" = "yes")

AC_CHECK_LIB([dl], [dlopen], [LIBDL_LIBS="-ldl"], [AC_MSG_ERROR([Could not find libdl])])
AC_SUBST(LIBDL_LIBS)
AC_CHECK_LIB([jpeg], [jpeg_set_defaults], [LIBJPEG_LIBS="-ljpeg"], [AC_MSG_ERROR([Could not find libjpeg])])
AC_SUBST(LIBJPEG_LIBS)
AC_CHECK_LIB([ungif], [DGifOpen], [LIBGIF_LIBS="-lungif"], [AC_CHECK_LIB([gif], [DGifOpen], [LIBGIF_LIBS="-lgif"], [AC_MSG_ERROR([Could not find libgif or libungif])])])
AC_SUBST(LIBGIF_LIBS)

AC_ARG_WITH(libsdl,
	AS_HELP_STRING([--with-libsdl],[use libsdl, yes or no]),
	[with_libsdl=$withval],[with_libsdl=no])
if test "$with_libsdl" = "yes"; then
	PKG_CHECK_MODULES(LIBSDL, sdl2)
	AC_DEFINE([HAVE_LIBSDL],[1],[Define to 1 to build the SDL2 display and input for PC])
fi
AM_CONDITIONAL(HAVE_LIBSDL, test "$with_libsdl" = "yes")

dnl HiSilicon 2D engine (TDE) on the u5x boxes, through libhiaccel from the dinobot-libs package.
dnl Only the code is built: lib/gdi/accel.cpp loads libhiaccel.so with dlopen at start, when the box has the engine
dnl and the setting is on; nothing is needed at build time and a box without the library draws with the CPU.
AC_ARG_WITH(libhiaccel,
	AS_HELP_STRING([--with-libhiaccel],[build the HiSilicon 2D engine (TDE) support, loaded at run time from libhiaccel.so, yes or no]),
	[with_libhiaccel=$withval],[with_libhiaccel=no])
if test "$with_libhiaccel" = "yes"; then
	AC_DEFINE([HAVE_HISILICON_ACCEL],[1],[Define to 1 to use the HiSilicon 2D engine (TDE) through libhiaccel.so, loaded with dlopen])
fi

dnl Machine name from the build recipe (MACHINE). On the HiSilicon boxes below video0 and audio0 of the first decoder
dnl drive the same player. lib/dvb/decoder.cpp then selects source 0xff for still pictures (radio background, RaSS),
dnl which puts them on the separate picture player: source MEMORY would rebuild the shared player without audio.
dnl "nobox" is the PC build. Any other value, or no value, defines nothing. --with-libhiaccel is only for HiSilicon
dnl boxes and the PC build, so together with any other value, or no value, configure stops: a HiSilicon image built
dnl without this path has no sound on radio channels.
AC_ARG_WITH(boxtype,
	AS_HELP_STRING([--with-boxtype=NAME],[machine name (MACHINE), used to select the HiSilicon decoder path; nobox for a PC build]),
	[BOXTYPE="$withval"],[BOXTYPE="none"])
AC_MSG_CHECKING([whether boxtype $BOXTYPE uses the HiSilicon still picture path])
case "$BOXTYPE" in
	u5|u5pvr|u51|u52|u54|u55|u56|u57|u571|u41|u42|u43|u45|u53|u532|u533|\
	sf8008|sf8008m|sx988|ip8|ustym4kpro|ustym4kottpremium|ustym4ks2ottx|gbmv200|beyonwizv2|viper4k|dagsmv200|og2ott4k|og2s4k|sfx6008|sx88v2)
		AC_DEFINE([HAVE_HISILICON],[1],[Define to 1 on HiSilicon boxes where video0 and audio0 share one player])
		AC_MSG_RESULT([yes])
		;;
	*)
		AC_MSG_RESULT([no])
		if test "$with_libhiaccel" = "yes" && test "$BOXTYPE" != "nobox"; then
			AC_MSG_ERROR([--with-libhiaccel needs --with-boxtype=MACHINE with a HiSilicon machine name, or --with-boxtype=nobox for a PC build (boxtype now: $BOXTYPE)])
		fi
		;;
esac

dnl The boards on which the platform daemon is libreader (Octagon SF8008 4K UHD, SF8008 MINI 4K, the first Amiko Viper
dnl 4K). Their showiframe is a plain program: it selects source MEMORY on video0, writes the picture and exits without
dnl selecting the demux again, so video0 stays on MEMORY after the backdrop. The images made for these boards select the
dnl demux source when a decoder is opened (lib/dvb/decoder.cpp). The Viper 4K V20, V30 and V40 (u5/u4, where showiframe
dnl is the daemon and one source serves all decoders) and every other machine define nothing.
AC_MSG_CHECKING([whether boxtype $BOXTYPE is a board with libreader])
case "$BOXTYPE" in
	viper4k|sf8008|sf8008m)
		AC_DEFINE([HAVE_HISILICON_LIBREADER],[1],[Define to 1 on the HiSilicon boards with libreader (viper4k, sf8008, sf8008m): a decoder selects the demux source when it is opened])
		AC_MSG_RESULT([yes])
		;;
	*)
		AC_MSG_RESULT([no])
		;;
esac

AC_ARG_WITH(debug,
	AS_HELP_STRING([--without-debug],[disable debugging code]),
	[with_debug="$withval"],[with_debug="yes"])
if test "$with_debug" = "yes"; then
	DEBUG_CFLAGS="-ggdb3"
	AC_DEFINE([DEBUG],[1],[Define to 1 to enable debugging code])
fi

AC_ARG_WITH(memcheck,
	AS_HELP_STRING([--with-memcheck],[enable memory leak checks]),
	[with_memcheck="$withval"],[with_memcheck="no"])
if test "$with_memcheck" = "yes"; then
	AC_DEFINE([MEMLEAK_CHECK],[1],[Define to 1 to enable memory leak checks])
fi

AC_ARG_WITH(po,
	AS_HELP_STRING([--with-po],[enable updating of po files]),
	[with_po="$withval"],[with_po="no"])
if test "$with_po" = "yes"; then
	AC_PATH_PROG(MSGINIT, msginit)
	AC_PATH_PROG(MSGMERGE, msgmerge)
	AC_PATH_PROG(MSGUNIQ, msguniq)
	AC_PATH_PROG(XGETTEXT, xgettext)
	if test -z "$MSGINIT" -o -z "$MSGMERGE" -o -z "$MSGUNIQ" -o -z "$XGETTEXT"; then
		AC_MSG_ERROR([Could not find required gettext tools])
	fi
fi
AM_CONDITIONAL(UPDATE_PO, test "$with_po" = "yes")

ENIGMA2_CFLAGS="-fno-rtti -fno-exceptions"
AC_SUBST(ENIGMA2_CFLAGS)

CPPFLAGS="$CPPFLAGS $PYTHON_CPPFLAGS"
CFLAGS="$CFLAGS $DEBUG_CFLAGS -Wall"
CXXFLAGS="$CXXFLAGS $DEBUG_CFLAGS -Wall $BASE_CFLAGS $GSTREAMER_CFLAGS $ENIGMA2_CFLAGS $PTHREAD_CFLAGS"

AC_CONFIG_FILES([
Makefile
data/Makefile
data/fonts/Makefile
data/countries/Makefile
data/defaults/Makefile
data/defaults/Dream/Makefile
data/defaults/Dream/hdbouquets/Makefile
data/defaults/Dream/sdbouquets/Makefile
data/extensions/Makefile
data/keymaps/Makefile
data/skin_default/Makefile
data/skin_default/menu/Makefile
data/skin_default/icons/Makefile
data/skin_default/buttons/Makefile
data/skin_default/spinner/Makefile
include/Makefile
lib/Makefile
lib/actions/Makefile
lib/base/Makefile
lib/base/eenv.cpp
lib/driver/Makefile
lib/dvb/Makefile
lib/dvb/lowlevel/Makefile
lib/dvb_ci/Makefile
lib/gdi/Makefile
lib/gui/Makefile
lib/mmi/Makefile
lib/nav/Makefile
lib/python/Makefile
lib/python/Components/Makefile
lib/python/Components/Converter/Makefile
lib/python/Components/Renderer/Makefile
lib/python/Components/Sources/Makefile
lib/python/Hds/Makefile
lib/python/Hds/DabT2/Makefile
lib/python/Hds/DabT2/t2/bin/Makefile
lib/python/Screens/Makefile
lib/python/Plugins/Makefile
lib/python/Plugins/Extensions/Makefile
lib/python/Plugins/Extensions/MediaPlayer/Makefile
lib/python/Plugins/Extensions/MediaPlayer/meta/Makefile
lib/python/Plugins/Extensions/MediaScanner/Makefile
lib/python/Plugins/Extensions/MediaScanner/meta/Makefile
lib/python/Plugins/Extensions/PicturePlayer/Makefile
lib/python/Plugins/Extensions/PicturePlayer/meta/Makefile
lib/python/Plugins/Extensions/PicturePlayer/data/Makefile
lib/python/Plugins/Extensions/HdsImportSetari/Makefile
lib/python/Plugins/Extensions/HdsWebControl/Makefile
lib/python/Components/HdsSubtitrariInternet/Makefile
lib/python/Components/HdsSubtitrariInternet/surse/Makefile
lib/python/Plugins/Extensions/HdsCutListEditor/Makefile
lib/python/Plugins/Extensions/HdsNavigator/Makefile
lib/python/Plugins/SystemPlugins/DiseqcTester/Makefile
lib/python/Plugins/SystemPlugins/DiseqcTester/meta/Makefile
lib/python/Plugins/SystemPlugins/Hotplug/Makefile
lib/python/Plugins/SystemPlugins/HdsDvbI/Makefile
lib/python/Plugins/SystemPlugins/Makefile
lib/python/Plugins/SystemPlugins/SkinSelector/Makefile
lib/python/Plugins/SystemPlugins/SkinSelector/meta/Makefile
lib/python/Tools/Makefile
lib/service/Makefile
lib/components/Makefile
po/Makefile
main/Makefile
tools/Makefile
tools/enigma2.sh
tools/hds-rezerva.sh
enigma2.pc
])
AC_OUTPUT
