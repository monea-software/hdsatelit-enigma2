# Modificat de moneasoftware.com si hdsatelit.com, 2026
dist_noinst_SCRIPTS = xml2po.py

LANGS = ar ca cs da de el en es et fi fr fy hr hu is it lt lv nl no pl pt ro ru sv sk sl sr tr uk
LANGMO = $(LANGS:=.mo)
LANGPO = $(LANGS:=.po)

EXTRA_DIST = $(LANGPO)

if UPDATE_PO
# the TRANSLATORS: allows putting translation comments before the to-be-translated line.
# _t: functia de traducere a modulelor care merg si fara enigma2 (probele de pe PC);
# N_: marcaj fara efect pentru textele din tabele, traduse abia la afisare.
# 0.3.2: si Components/HdsSubtitrariInternet (cu surse/), descarcarea subtitrarilor, mutata din dosarul de plugin.
enigma2-py.pot: $(top_srcdir)/*.py $(top_srcdir)/lib/python/*/*.py $(top_srcdir)/lib/python/Hds/*/*.py $(top_srcdir)/lib/python/Plugins/*/*/*.py $(top_srcdir)/lib/python/Plugins/*/*/*/*.py $(top_srcdir)/lib/python/Components/HdsSubtitrariInternet/*.py $(top_srcdir)/lib/python/Components/HdsSubtitrariInternet/surse/*.py
	$(XGETTEXT) -L Python --from-code=UTF-8 --add-comments="TRANSLATORS:" --keyword=_t --keyword=N_ -d @PACKAGE_NAME@ -s -o $@ $^

enigma2-xml.pot: $(srcdir)/xml2po.py $(wildcard $(top_srcdir)/data/*.xml $(top_srcdir)/lib/python/Plugins/SystemPlugins/*/*.xml)
	$(PYTHON) $^ > $@

enigma2.pot: enigma2-py.pot enigma2-xml.pot
	cat $^ | $(MSGUNIQ) --no-location -o $@ -

%.po: enigma2.pot
	if [ -f $@ ]; then \
		$(MSGMERGE) --backup=none --no-location -s -N -U $@ $< && touch $@; \
	else \
		$(MSGINIT) -l $@ -o $@ -i $< --no-translator; \
	fi
endif

.po.mo:
	$(MSGFMT) -o $@ $<

BUILT_SOURCES = $(LANGMO)
CLEANFILES = $(LANGMO) enigma2-py.pot enigma2-xml.pot enigma2.pot

dist-hook: $(LANGPO)

install-data-local: $(LANGMO)
	for lang in $(LANGS); do \
		$(mkinstalldirs) $(DESTDIR)$(pkgdatadir)/po/$$lang/LC_MESSAGES; \
		$(INSTALL_DATA) $$lang.mo $(DESTDIR)$(pkgdatadir)/po/$$lang/LC_MESSAGES/@PACKAGE_NAME@.mo; \
	done

uninstall-local:
	for lang in $(LANGS); do \
		$(RM) $(DESTDIR)$(pkgdatadir)/po/$$lang/LC_MESSAGES/@PACKAGE_NAME@.mo; \
	done
