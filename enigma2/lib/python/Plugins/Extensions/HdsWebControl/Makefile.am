installdir = $(pkglibdir)/python/Plugins/Extensions/HdsWebControl

install_PYTHON = \
	__init__.py \
	accel_web.py \
	acces_conditionat_web.py \
	acces_ssh_web.py \
	acces_web.py \
	pasi_decriptare_web.py \
	actualizare_web.py \
	actualizari_web.py \
	afisaj_web.py \
	antena_web.py \
	aplicatii_web.py \
	asociere.py \
	aspect_web.py \
	cadru_web.py \
	captura_sigura.py \
	calitate_imagine_web.py \
	canale_web.py \
	cauta_setari_web.py \
	cautare_web.py \
	vezi_live_web.py \
	ceas_web.py \
	culegere_canale_web.py \
	culori_web.py \
	copie_setari_web.py \
	dabt2_web.py \
	descarcare_subtitrari_web.py \
	ecran_negru_web.py \
	ecran_pornire_web.py \
	egalizator_web.py \
	filme_web.py \
	font_interfata_web.py \
	ghid_web.py \
	informatii_web.py \
	informatii_tabel_web.py \
	jurnal_web.py \
	licente_web.py \
	limba_interfata_web.py \
	limbi_web.py \
	marime_text_web.py \
	margini_web.py \
	meniu_web.py \
	meniu_comun_web.py \
	meniu_pagini_web.py \
	alimentare_web.py \
	resetare_web.py \
	parental_web.py \
	disc_web.py \
	jurnale_sistem_web.py \
	canal_info_web.py \
	retea_web.py \
	unelte_retea_web.py \
	internet_web.py \
	intrari_web.py \
	media_web.py \
	extensii_web.py \
	diseqc_web.py \
	navigator_web.py \
	mod_sigur_web.py \
	mouse_web.py \
	ocr_limbi_web.py \
	paza_model_web.py \
	paznic_web.py \
	tv_web.py \
	osd_strat.py \
	acces_extern.py \
	aparate_web.py \
	betatester_web.py \
	playlisturi_web.py \
	piste.py \
	plugin.py \
	portal_web.py \
	procesor_web.py \
	radio_web.py \
	scanare_import_web.py \
	scanare_liste_web.py \
	scanare_web.py \
	setari_copie_web.py \
	setari_web.py \
	stocare_web.py \
	locuri_retea_web.py \
	subtitrari_film_web.py \
	teletext_web.py \
	sunet_web.py \
	volum_intarziere_web.py \
	standby_tv_web.py \
	stare_retea_web.py \
	telecomenzi_web.py \
	temporizatoare_web.py \
	tema_tv_web.py \
	traducere_pagini.py \
	video_web.py \
	vpn_web.py \
	asistenta_web.py \
	subtitrari_web.py \
	traducere_subtitrari_web.py \
	traducere_configurare_web.py \
	traducere_hbbtv_web.py

# TV in browser: mpegts.js 1.8.0 (Apache-2.0, modificat: schimbarile in mpegts-licenta.txt) si licenta lui, servite
# de tv_web.py la /tv/; mouse-ecran.js: mouse-ul pe ecran si telecomanda pe ecranul intreg in panou, pus in pagina
# de mouse_web.py; hds-sunet.js: sunetul AC-3 al canalelor H.264 / HEVC decodat in pagina (decodorul din tv-wasm/)
# si dat lui mpegts.js ca FLAC (cod propriu, GPL-2.0-only)
install_DATA = \
	mpegts.js \
	mpegts-licenta.txt \
	player.js \
	mouse-ecran.js \
	hds-player.js \
	hds-worker.js \
	hds-sunet.js

# TV in browser, canalele MPEG-2: playerul wasm (hds-player.js, hds-worker.js, mai sus: cod propriu, GPL-2.0-only) si
# decodorul lui, servit de tv_web.py la /tv/tv-wasm/: FFmpeg 8.1.3 (libavcodec, LGPL-2.1-or-later, fara
# --enable-gpl) cu emscripten 6.0.9, construit gata de tv-wasm/construieste-decodor-wasm.sh din tv-wasm/hdsdec.c
# (OpenEmbedded nu are emscripten), cu licentele lui. sha256:
#   tv-wasm/hdsdec.wasm  099cf027855f9659157e28a26a2c3cc0e8ba46d50d387bdd2007299127ea4711
#   tv-wasm/hdsdec.js    8688f27f8b55bada8a4e73083f01001a4753118c5a2fa62c2d149c1bf3ceb374
tvwasmdir = $(installdir)/tv-wasm
tvwasm_DATA = \
	tv-wasm/hdsdec.wasm \
	tv-wasm/hdsdec.js \
	tv-wasm/ffmpeg-licenta.txt \
	tv-wasm/emscripten-licenta.txt \
	tv-wasm/musl-licenta.txt \
	tv-wasm/compiler-rt-licenta.txt \
	tv-wasm/dlmalloc-licenta.txt
