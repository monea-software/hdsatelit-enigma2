# Modificat de moneasoftware.com si hdsatelit.com, 2026
dnl Detectarea antetelor DVB.
dnl Rescris pentru HDSatelit Image (Monea Software, 2026): versiunea API se citeste
dnl cu AC_COMPUTE_INT; metoda veche prin preprocesor nu mai merge cu compilatoarele noi.
AC_DEFUN([TUXBOX_APPS_DVB],[
AC_ARG_WITH(dvbincludes,
	[  --with-dvbincludes=PATH  path for dvb includes [[NONE]]],
	[DVBINCLUDES="$withval"],[DVBINCLUDES=""])

if test "$DVBINCLUDES"; then
	CPPFLAGS="$CPPFLAGS -I$DVBINCLUDES"
fi

DVB_API_VERSION=""
AC_CHECK_HEADERS([linux/dvb/version.h],[
	AC_COMPUTE_INT([DVB_API_VERSION], [DVB_API_VERSION], [#include <linux/dvb/version.h>], [DVB_API_VERSION=""])
])

if test -n "$DVB_API_VERSION"; then
	AC_MSG_NOTICE([found dvb api version $DVB_API_VERSION])
	AC_DEFINE(HAVE_DVB,1,[Define to 1 if you have the dvb includes])
	AC_DEFINE_UNQUOTED(HAVE_DVB_API_VERSION,$DVB_API_VERSION,[Define to the version of the dvb api])
else
	AC_MSG_ERROR([can't find dvb headers])
fi
])
