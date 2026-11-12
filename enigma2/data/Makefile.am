# Modificat de moneasoftware.com si hdsatelit.com, 2026
SUBDIRS = countries fonts defaults extensions keymaps skin_default

# SoftCSA (lib/dvb/cahandler.h): semnul ca enigma2 serveste /tmp/.listen.camd.socket si ia cuvintele de control prin
# protocolul 3. Scriptul de pornire al modulelor de acces trece atunci singur pe pmt_mode = 6 si extended_cw_api = 1
# (si inapoi cand semnul lipseste); vine numai cu acest cod, deci pleaca singur cu o imagine fara SoftCSA.
# Pe toate receptoarele (HDS_SOFTCSA din configure.ac: orice masina, HiSilicon pe drumul lui, celelalte pe cel obisnuit);
# numai constructia de PC (nobox) ramane fara semn, deci acolo modulele raman pe drumul vechi (pmt_mode 0, /tmp/camd.socket).
softcsadir = $(datadir)/hdsatelit
if HDS_SOFTCSA
dist_softcsa_DATA = softcsa
else
EXTRA_DIST = softcsa
endif

# Afisajul propriu se instaleaza impreuna cu alegerea lui din skin.py.
hdsdisplaydir = $(pkgdatadir)/HDSatelit/display
dist_hdsdisplay_DATA = $(top_srcdir)/HDSatelit/display/skin_display.xml

dist_pkgdata_DATA = \
	cablu-romania.json \
	defaultsatlists.xml \
	defaultwizard.xml \
	dreampackagewizard.xml \
	encoding.conf \
	hds-baza-pornire.jsonl.gz \
	hds-cursor-mouse.png \
	hds-drivere-pachete.json \
	hds-module-pachete.json \
	hds-producatori-mac.txt.gz \
	hbbtv-aplicatii.json \
	jurnal-versiuni.json \
	keymap.xml \
	menu.xml \
	multumiri-producatori.json \
	multumiri-testeri.json \
	nota-testeri.json \
	operatori-satelit.json \
	prev.png \
	radio.mvi \
	rcpositions.xml \
	setup.xml \
	skin_default.xml \
	skin.xml \
	telecomanda-viper.json \
	telecomanda-viper.png \
	telecomanda-viper.svg \
	terestru-romania.json \
	tutorialwizard.xml \
	unicable.xml

# catalogul Asistentei de la distanta (data/asistenta/catalog.json -> ${datadir}/enigma2/asistenta/catalog.json);
# nobase pastreaza subdosarul (Components/HdsAsistentaCatalog.py il citeste de acolo)
nobase_dist_pkgdata_DATA = \
	asistenta/catalog.json \
	vremea/soare.png \
	vremea/nori.png \
	vremea/ploaie.png \
	vremea/zapada.png \
	vremea/ceata.png \
	vremea/furtuna.png \
	vremea/noapte.png \
	vremea/surse.json

# Copia din pachet ramane disponibila pentru revenirea din galerie.
sigleoriginaledir = $(pkgdatadir)/sigle-pornire
dist_sigleoriginale_DATA = sigle-pornire/radio.mvi
