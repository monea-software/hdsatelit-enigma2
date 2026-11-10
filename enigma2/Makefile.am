# Modificat de moneasoftware.com si hdsatelit.com, 2026
SUBDIRS = include lib main data po tools

ACLOCAL_AMFLAGS = -I m4

installdir = $(pkglibdir)/python
install_PYTHON = \
	Navigation.py NavigationInstance.py RecordTimer.py SleepTimer.py ServiceReference.py \
	keyids.py keymapparser.py mytest.py skin.py timer.py tools.py GlobalActions.py \
	e2reactor.py boxbranding.py

pkgconfigdir = $(libdir)/pkgconfig
pkgconfig_DATA = enigma2.pc

metadir = $(datadir)/meta
meta_DATA = index-enigma2.xml
CLEANFILES = index-enigma2.xml

EXTRA_DIST = lamedb

# Pozele afisajului se instaleaza si la compilarea separata a interfetei.
EXTRA_DIST += $(shell find $(srcdir)/HDSatelit/afisaj-color -type f)

# Identificatorul sursei ramane version=0<versiune><data commit>, cu 16/19 cifre.
# Data instalarii pachetului, UTC, sta separat in imagebuild si date.
# enigma.info ofera numele complet si versiunea citibila listelor de pornire.
# Peste 99 pe o parte sau zerouri in fata (0.3.09) opresc constructia.
install-data-hook:
	$(MKDIR_P) $(DESTDIR)$(sysconfdir)
	$(MKDIR_P) $(DESTDIR)$(datadir)/enigma2/HDSatelit/afisaj-color
	cp -R $(srcdir)/HDSatelit/afisaj-color/480x320 \
		$(srcdir)/HDSatelit/afisaj-color/400x240 \
		$(srcdir)/HDSatelit/afisaj-color/orbita \
		$(srcdir)/HDSatelit/afisaj-color/fonturi \
		$(DESTDIR)$(datadir)/enigma2/HDSatelit/afisaj-color/
	v=`echo $(PACKAGE_VERSION) | tr -d .`; \
	echo "$(PACKAGE_VERSION)" | grep -Eq '^(0|[1-9][0-9]?)\.(0|[1-9][0-9]?)\.(0|[1-9][0-9]?)$$' || { \
		echo "versiunea $(PACKAGE_VERSION) nu incape in /etc/image-version (x.y.z, cel mult 99 pe parte)" >&2; exit 1; }; \
	echo "$(PACKAGE_VERSION)" | grep -Eq '^[0-9]\.[0-9]\.[0-9]$$' || \
		v=`echo $(PACKAGE_VERSION) | awk -F. '{ printf "%02d%02d%02d", $$1, $$2, $$3 }'`; \
	d=`git -c safe.directory="*" -C $(top_srcdir) log -1 --format=%cd --date=format:%Y%m%d%H%M 2>/dev/null`; \
	[ -n "$$d" ] || d=`date +%Y%m%d%H%M`; \
	b=`date -u +%Y%m%d%H%M%S`; \
	printf '%s\n' "version=0$$v$$d" "creator=HD Satelit" \
		"imagename=HD Satelit" "imageversion=$(PACKAGE_VERSION)" \
		"imagebuild=$${b%??????}" "date=$$b" "distro=hdsatelit" \
		"url=https://hdsatelit.com" > "$(DESTDIR)$(sysconfdir)/image-version"; \
	$(MKDIR_P) "$(DESTDIR)$(libdir)"; \
	printf '%s\n' "distro='hdsatelit'" "displaydistro='HD Satelit'" \
		"imgversion='$(PACKAGE_VERSION)'" "imageversion='$(PACKAGE_VERSION)'" \
		"imagebuild='$${b%??????}'" "compiledate='$${b%??????}'" \
		> "$(DESTDIR)$(libdir)/enigma.info"; \
	c=`md5sum "$(DESTDIR)$(libdir)/enigma.info" | cut -d ' ' -f 1`; \
	printf 'checksum=%s\n' "$$c" >> "$(DESTDIR)$(libdir)/enigma.info"

index-enigma2.xml: $(top_srcdir)/tools/genmetaindex.py $(top_srcdir)/lib/python/Plugins/*/*/meta/plugin_*.xml
	$(AM_V_GEN)$(PYTHON) $^ > $@
