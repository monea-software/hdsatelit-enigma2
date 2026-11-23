installdir = $(pkglibdir)/python/Plugins/Extensions/HdsWebControl

install_PYTHON = \
	__init__.py \
	bluetooth_web.py \
	accel_web.py \
	acces_conditionat_web.py \
	porturi_web.py \
	acces_ssh_web.py \
	acces_web.py \
	pasi_decriptare_web.py \
	actualizare_web.py imagine_online_web.py \
	actualizari_web.py \
	partea_doua_web.py \
	afisaj_web.py \
	ajutor_web.py \
	antena_web.py \
	aplicatii_web.py \
	asociere.py \
	montare_web.py \
	aspect_web.py \
	cadru_web.py \
	captura_sigura.py \
	calitate_imagine_web.py \
	canale_web.py \
	editor_canale_web.py \
	cauta_setari_web.py \
	cautare_web.py \
	vezi_live_web.py \
	ceas_web.py \
	ci_web.py \
	functii_imagine_web.py \
	culegere_canale_web.py \
	culori_web.py \
	copie_setari_web.py \
	copie_imagine_web.py \
	dabt2_web.py \
	dab_usb_web.py \
	oarba_web.py \
	descarcare_subtitrari_web.py \
	ecran_negru_web.py \
	ecran_pornire_web.py \
	galerie_sigle_web.py \
	piconuri_web.py \
	mozaic_web.py \
	despre_film_web.py \
	sport_azi_web.py \
	ghid_internet_web.py \
	screensaver_web.py \
	egalizator_web.py \
	filme_web.py \
	flux_transcodare_web.py \
	font_interfata_web.py \
	forum_web.py \
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
	fisiere_core.py \
	fisiere_web.py \
	https_web.py \
	fisiere_pagina.py \
	media_web.py \
	extensii_web.py \
	diseqc_web.py \
	navigator_web.py \
	aplicatii_tv_web.py \
	mod_sigur_web.py \
	mouse_web.py \
	ocr_limbi_web.py \
	paza_model_web.py \
	paznic_web.py \
	sloturi_web.py \
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
	radio_live_web.py \
	radio_online_web.py \
	filme_seriale_web.py \
	scanare_import_web.py \
	scanare_liste_web.py \
	liste_internet_web.py \
	scanare_web.py \
	setari_copie_web.py \
	setari_web.py \
	setari_deschise_web.py \
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
	tema_export.py \
	vremea_web.py \
	traducere_pagini.py \
	video_web.py \
	vpn_web.py \
	vpn_furnizori_web.py \
	asistenta_web.py \
	subtitrari_web.py \
	traducere_subtitrari_web.py \
	vorbire_web.py \
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

# TV in browser, canalele MPEG-2 (si H.264 in browserele fara H.264 in MediaSource): playerul wasm (hds-player.js,
# hds-worker.js, mai sus: cod propriu, GPL-2.0-only) si decodorul lui, servit de tv_web.py la /tv/tv-wasm/: FFmpeg
# 8.1.3 (libavcodec, LGPL-2.1-or-later, fara --enable-gpl) cu emscripten 6.0.9, construit gata de
# tv-wasm/construieste-decodor-wasm.sh din tv-wasm/hdsdec.c cu HDS_DEC_EXTRA=h264,aac (OpenEmbedded nu are
# emscripten), cu licentele lui si lista decodoarelor din el (decodoare.txt: receptorul o citeste ca sa stie ce canale
# merg pe playerul wasm, de pilda H.264 numai cand decodorul il are). sha256:
#   tv-wasm/hdsdec.wasm  e835a97f572579072f36517ca9b116332e22c686149da9b0f6b449abf2d40c16
#   tv-wasm/hdsdec.js    06803f384c5927ecba285b627e892c944772eef7856df5f3a0fb5c551192a157
tvwasmdir = $(installdir)/tv-wasm
tvwasm_DATA = \
	tv-wasm/hdsdec.wasm \
	tv-wasm/hdsdec.js \
	tv-wasm/decodoare.txt \
	tv-wasm/ffmpeg-licenta.txt \
	tv-wasm/emscripten-licenta.txt \
	tv-wasm/musl-licenta.txt \
	tv-wasm/compiler-rt-licenta.txt \
	tv-wasm/dlmalloc-licenta.txt
