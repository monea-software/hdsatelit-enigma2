# Modificat de moneasoftware.com si hdsatelit.com, 2026
SUBDIRS = countries fonts defaults extensions keymaps skin_default

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
	hds-module-pachete.json \
	hds-producatori-mac.txt.gz \
	hbbtv-aplicatii.json \
	jurnal-versiuni.json \
	keymap.xml \
	menu.xml \
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
