# Modificat de moneasoftware.com si hdsatelit.com, 2026
SUBDIRS = include lib main data po tools

ACLOCAL_AMFLAGS = -I m4

installdir = $(pkglibdir)/python
install_PYTHON = \
	Navigation.py NavigationInstance.py RecordTimer.py SleepTimer.py ServiceReference.py \
	keyids.py keymapparser.py mytest.py skin.py timer.py tools.py GlobalActions.py \
	e2reactor.py

pkgconfigdir = $(libdir)/pkgconfig
pkgconfig_DATA = enigma2.pc

metadir = $(datadir)/meta
meta_DATA = index-enigma2.xml
CLEANFILES = index-enigma2.xml

EXTRA_DIST = lamedb

# /etc/image-version pentru ecranul About: version=0<major><minor><revizie><data commit>, 16 cifre cand fiecare parte a
# versiunii are o cifra (0.3.9 -> 0039...); cand o parte are doua cifre, fiecare parte sta pe doua cifre, 19 cifre
# (0.3.10 -> 0000310...). Cititorii (Components/HdsJurnalVersiuni.desparte_build, About, cadru_web, HdsCommon) le stiu
# pe amandoua; peste 99 pe o parte sau o parte cu 0 in fata (0.3.09) opresc constructia.
install-data-hook:
	$(MKDIR_P) $(DESTDIR)$(sysconfdir)
	v=`echo $(PACKAGE_VERSION) | tr -d .`; \
	echo "$(PACKAGE_VERSION)" | grep -Eq '^(0|[1-9][0-9]?)\.(0|[1-9][0-9]?)\.(0|[1-9][0-9]?)$$' || { \
		echo "versiunea $(PACKAGE_VERSION) nu incape in /etc/image-version (x.y.z, cel mult 99 pe parte)" >&2; exit 1; }; \
	echo "$(PACKAGE_VERSION)" | grep -Eq '^[0-9]\.[0-9]\.[0-9]$$' || \
		v=`echo $(PACKAGE_VERSION) | awk -F. '{ printf "%02d%02d%02d", $$1, $$2, $$3 }'`; \
	d=`git -c safe.directory="*" -C $(top_srcdir) log -1 --format=%cd --date=format:%Y%m%d%H%M 2>/dev/null`; \
	[ -n "$$d" ] || d=`date +%Y%m%d%H%M`; \
	printf "version=0%s%s\ndistro=hdsatelit\nurl=https://hdsatelit.com\n" "$$v" "$$d" > $(DESTDIR)$(sysconfdir)/image-version

index-enigma2.xml: $(top_srcdir)/tools/genmetaindex.py $(top_srcdir)/lib/python/Plugins/*/*/meta/plugin_*.xml
	$(AM_V_GEN)$(PYTHON) $^ > $@
