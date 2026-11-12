# Modificat de moneasoftware.com si hdsatelit.com, 2026
installdir = $(datadir)/fonts

# licentele stau langa fonturi (Atkinson Hyperlegible, Barlow, PT Sans: neschimbate, din google/fonts, OFL 1.1); „Console” e DejaVu Sans Mono Bold (are ă ș ț),
# tuxtxt.ttf (Bitstream Vera Sans Mono Bold 1.10, neschimbat) ramane pentru teletext, cu licenta Vera langa el
# enigma2icons.ttf: fontul nostru de pictograme cu codurile asteptate de temele si pluginurile OE-Alliance (alias "enigma2icons",
# inregistrat in skin_default.xml); desenele din Material Symbols (Apache 2.0), licenta langa el; refacut de
# hdsatelit-unelte/receptor/imagine-hdsatelit/unelte/font_pictograme/fa_font.py
dist_install_DATA = \
	ae_AlMateen.ttf \
	AtkinsonHyperlegible-Regular.ttf \
	AtkinsonHyperlegible-Bold.ttf \
	AtkinsonHyperlegible-OFL.txt \
	Barlow-Regular.ttf \
	Barlow-Bold.ttf \
	BarlowSemiCondensed-Regular.ttf \
	Barlow-OFL.txt \
	ae_AlMateen.license \
	DejaVuSansMono-Bold.ttf \
	DejaVuSansMono-Bold.license \
	enigma2icons.ttf \
	enigma2icons.license \
	HdsRegular.ttf \
	HdsBold.ttf \
	HdsCond.ttf \
	OFL.txt \
	PT_Sans-Web-Regular.ttf \
	PT_Sans-Web-Bold.ttf \
	PT_Sans-Narrow-Web-Regular.ttf \
	PT_Sans-OFL.txt \
	tuxtxt.ttf \
	tuxtxt.license

# fallback.font: fontul de rezerva (al treilea, dupa fontul textului si Replacement), numai pentru simbolurile cerute de
# pluginuri (sageti, buline, barele de nivel U+2581-2587, chenare). Legatura spre DejaVu Sans Mono Bold, care le are (licenta langa el,
# DejaVuSansMono-Bold.license): niciun octet in plus. lib/gdi/font.cpp il incarca singur; pluginurile il cer pe nume.
install-data-hook:
	cd $(DESTDIR)$(installdir) && rm -f fallback.font && ln -s DejaVuSansMono-Bold.ttf fallback.font
