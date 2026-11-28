# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Setarile comune ale ecranului si paginii /taste-rapide.
# Functia obisnuita lasa tasta pe hartile barei, dupa telecomanda si canal.
# Numele setarilor vechi raman valabile. Nicio dependenta nativa la import.

try:
	_
except NameError:
	def _(text):
		return text


def text_tasta(cheie, text, traducere=None):
	"""Textul unui rand din BUTOANE, SCURTE sau PROFIL_SETARI in limba de acum.

	Listele se fac la import, uneori inainte sa fie pusa traducerea enigma2; atunci _ e cel de rezerva de mai sus si
	randurile raman in romana (ecranul tastelor in turca pe Solo SE, Ozgur, 11.11.2026). De aceea se traduc din nou la
	afisare; un text deja tradus trece neschimbat. traducere: functia paginii web (altfel cea a enigma2)."""
	t = traducere
	if t is None:
		try:
			import builtins
			t = builtins._
		except (AttributeError, ImportError):
			return text
	if cheie.startswith("number_") and cheie.endswith("_long"):
		try:
			return t("%d (apăsare lungă)") % int(cheie.split("_")[1])
		except (TypeError, ValueError):
			return text
	return t(text)


def _tr(text):
	"""Traducerea enigma2 de acum (alegerile si textele actiunilor, facute la import; vezi text_tasta)."""
	return text_tasta("", text)


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele date lui _tr se traduc la folosire."""
	return text


ACTIUNI_DISPONIBILE = [
	("default", _("Funcția obișnuită")),
	("none", _("Nimic")),
	# Ozgur (Solo SE, 11.11.2026): SUS/JOS schimba canalul, STANGA/DREAPTA volumul. Aceleasi texte ca in TEXTE_ACTIUNI.
	("zap_next", _("Canalul următor")),
	("zap_previous", _("Canalul anterior")),
	("volume_up", _("Mai tare")),
	("volume_down", _("Mai încet")),
	("epg", _("Alegerea tipului de ghid (EPG)")),
	("epg_multi", _("Ghidul buchetului curent")),
	("epg_single", _("Ghidul canalului curent")),
	("epg_grafic", _("Ghid grafic")),
	("eventinfo", _("Detaliile emisiunii")),
	("subtitle_toggle", _("Pornește sau oprește ultima subtitrare")),
	("portal", _("Portal")),
	("menu", _("Meniu principal")),
	("plugins", _("Plugins")),
	("extensions", _("Lista extensiilor (ca ALBASTRU)")),
	("info", _("Informații sistem")),
	# ecranul VPN (Screens/HdsVpn.py, Setari > Retea & Internet > VPN) dintr-o tasta (tamiciav7, LinuxSat 164122
	# #970724); eticheta randului din meniu, deja tradusa
	("vpn", _("VPN")),
	("audio", _("Selectare pistă audio")),
	("subtitle", _("Subtitrări")),
	("channellist", _("Lista de canale")),
	("favourites", _("Favorite")),
	# lista deschisa direct in dosarul transponderului canalului de acum (tfrc, LinuxSat 164122 #970392); textul
	# OE-Alliance al randului din lista, deja tradus in toate limbile
	("current_transponder", _("Current Transponder")),
	# lista ultimelor canale vazute, din care alegi direct (Screens/HdsIstoricCanale.py); din fabrica pe < tinut apasat
	("channel_history", _("Canale recente")),
	# toate canalele TV ale transponderului canalului de acum pe 2, 4 sau 9 celule (Screens/HdsMozaic.py); din fabrica pe
	# 0 tinut apasat (Eduard 14.11.2026 21:06: o tasta cand esti pe canal)
	# prima bara de informatii fixa pe ecran pana la a doua apasare a aceleiasi taste (tfrc, LinuxSat 164191, CR4 0.7.8)
	("infobar_fixed", _("Bara de informații fixă (a doua apăsare o ascunde)")),
	("mozaic", _("Mozaic: toate canalele transponderului")),
	("movies", _("Înregistrări")),
	("record", _("Înregistrare imediată")),
	("timeshift", _("Pornește timeshift")),
	("timeshift_stop", _("Oprește timeshift")),
	("teletext", _("Teletext")),
	("subservices", _("Subcanale")),
	("pip", _("Pornește sau oprește PiP")),
	("timers", _("Înregistrări programate")),
	("standby", _("Standby")),
	("shutdown", _("Oprire receptor")),
	("reboot", _("Repornire receptor")),
	("restart", _("Repornire interfață")),
	# RLS6 (tfrc, LinuxSat 164126): fisierele temei (si skin_user*.xml) citite din nou, fara repornirea interfetei (skin.py)
	("reload_skin", _("Reîncarcă tema")),
	("captura", _("Captură de ecran")),
]

BUTOANE = [
	("red", _("Roșu (apăsare lungă)")),
	("green", _("Verde (apăsare lungă)")),
	("yellow", _("Galben (apăsare lungă)")),
	("blue", _("Albastru (apăsare lungă)")),
	("info_long", _("INFO (apăsare lungă)")),
	("epg_long", _("EPG (apăsare lungă)")),
	("subtitle_long", _("SUBTITLE (apăsare lungă)")),
	("audio_long", _("AUDIO (apăsare lungă)")),
	("fav_long", _("FAV (apăsare lungă)")),
	("previous_long", _("Canalul anterior < (apăsare lungă)")),
]
BUTOANE += [("number_%d_long" % n, _("%d (apăsare lungă)") % n)
	for n in range(10)]

SCURTE = [
	("red_short", _("Roșu (apăsare scurtă)")),
	("green_short", _("Verde (apăsare scurtă)")),
	("yellow_short", _("Galben (apăsare scurtă)")),
	("blue_short", _("Albastru (apăsare scurtă)")),
	("info_short", _("INFO")),
	("epg_short", _("EPG")),
	("up_short", _("Sus")),
	("down_short", _("Jos")),
	("left_short", _("Stânga")),
	("right_short", _("Dreapta")),
	("ok_short", _("OK")),
	("text_short", _("TEXT")),
	("audio_short", _("AUDIO")),
	("fav_short", _("FAV")),
	("video_short", _("PVR / VIDEO (înregistrări)")),
	("list_short", _("LIST (player media)")),
	("record_short", _("REC")),
	("play_short", _("PLAY")),
	("pause_short", _("PAUZĂ")),
	("stop_short", _("STOP")),
	("rewind_short", _("Derulare înapoi")),
	("forward_short", _("Derulare înainte")),
	("channelup_short", _("CH+")),
	("channeldown_short", _("CH-")),
	("subtitle_short", _("SUBT")),
	("menu_short", _("MENU")),
	("timer_short", _("TIMER")),
	("portal_short", _("PORTAL")),
	("tv_short", _("TV")),
	("radio_short", _("RADIO")),
	("previous_short", _("Canalul anterior (<)")),
	("next_short", _("Canalul următor (>)")),
]

# VERDE scurt deschide din fabrica Extensii si aplicatii (PluginBrowser), ca in celelalte imagini Enigma2; subcanalele
# raman in Lista extensiilor (ALBASTRU) cand canalul le are. Cine a ales altceva pentru VERDE isi pastreaza alegerea
# (config salveaza numai valorile diferite de fabrica). Aceeasi valoare pe televizor, in web (/taste-rapide) si in ajutor.
VALORI_IMPLICITE = dict((k, "default") for k, _text in SCURTE + BUTOANE)
VALORI_IMPLICITE.update(red="none", green="none", yellow="none",
	blue="none", green_short="plugins", yellow_short="audio", blue_short="extensions")

# Sensul functiei obisnuite se pastreaza intr-un singur loc.
FUNCTII_OBISNUITE = {
	"info_short": "eventinfo", "info_long": "epg",
	"epg_short": "epg_multi", "epg_long": "epg",
	"subtitle_short": "subtitle_toggle", "subtitle_long": "subtitle",
	"green_short": "plugins", "yellow_short": "audio", "blue_short": "extensions",
	"red": "none", "green": "none", "yellow": "none", "blue": "none",
	# < tinut apasat: lista canalelor recente; < scurt ramane canalul de dinainte din istoric, la eliberare
	"previous_long": "channel_history",
	# 0 tinut apasat: mozaicul canalelor transponderului (Eduard 14.11.2026 21:06: o tasta cand esti pe canal); 0 scurt
	# ramane canalul de dinainte, la eliberare. Culorile lungi raman fara alocare din fabrica (fisa 73, P7).
	"number_0_long": "mozaic",
}

# Tasta fizica, setarea scurta, setarea lunga, scurta la eliberare.
# Numerele pastreaza selectia canalului la apasare pana li se aloca ceva lung.
LEGATURI_TASTE = [
	("red", "red_short", "red", True),
	("green", "green_short", "green", True),
	("yellow", "yellow_short", "yellow", True),
	("blue", "blue_short", "blue", True),
	("info", "info_short", "info_long", True),
	("epg", "epg_short", "epg_long", True),
	("subtitle", "subtitle_short", "subtitle_long", True),
	("audio", "audio_short", "audio_long", True),
	("fav", "fav_short", "fav_long", True),
	("previous", "previous_short", "previous_long", True),
]
LEGATURI_TASTE += [(k[:-6], k, None, False) for k, _text in SCURTE
	if k not in [x[1] for x in LEGATURI_TASTE]]
LEGATURI_TASTE += [("number_%d" % n, None, "number_%d_long" % n, True)
	for n in range(10)]


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


# Setarile gesturilor din liste si meniuri. Nu se face migrare.
PROFIL_SETARI = (
	("hds_asezare_taste", "obisnuita", _("Așezarea tastelor")),
	("hds_fav_scurt_adauga", False, _("FAV scurt adaugă sau scoate canalul din Favorite")),
	("hds_ok_lung_cauta", False, _("OK lung caută în lista de canale")),
	("hds_text_lista_cauta", False, _("TEXT caută în lista de canale")),
	("hds_meniu_galben_aspect", False, _("GALBEN schimbă lista sau dalele în meniu")),
	("hds_meniu_text_cauta", False, _("TEXT caută setări în meniu")),
	("hds_filme_culori_vechi", False, _("Culorile vechi în lista de filme")),
	("hds_ch_privire", "device", _("CH+ și CH- la privit")),
	# NEU9 (skovemi, LinuxSat 164248 #972834): EXIT la privit, fara nimic pe ecran, arata bara (pentru asezarea Neutrino);
	# din fabrica o ascunde, ca pana acum (Screens/InfoBarGenerics.hdsIesirePrivire)
	("hds_exit_privire", "hide", _("EXIT cât te uiți la TV")),
	("hds_exit_film", "hide", _("EXIT în timpul filmului")),
	# 0.7.7 (LST, tamiciav7, LinuxSat 164182 #970755): EXIT in lista de canale; aceeasi setare si in Setări listă de canale
	# (data/setup.xml hds_lista_canale). Din fabrica ca pana acum (Screens/ChannelSelection.hdsTastaExit)
	("hds_exit_lista", "up", _("EXIT în lista de canale")),
	# 0.7.7: mouse-ul pus in receptor tine loc de telecomanda (Components/HdsMouseEcran: setareMouse, TASTE_MOUSE;
	# forumul 795 #2940): rotita la privit = volumul, clicul pe rotita = MENIU, butoanele laterale = Inapoi si Sunet
	# oprit, toate la alegere
	("hds_mouse_rotita", "volum", _("Rotița mouse-ului cât te uiți la TV")),
	("hds_mouse_mijloc", "meniu", _("Clicul pe rotița mouse-ului")),
	("hds_mouse_spate", "inapoi", _("Butonul lateral din spate al mouse-ului")),
	("hds_mouse_fata", "mut", _("Butonul lateral din față al mouse-ului")),
)
# alegerile se traduc la afisare (initConfigProfil, cand se deschide ecranul sau pagina /taste-rapide), nu la import:
# atunci limba poate lipsi inca si alegerile ramaneau in romana (asistenta 946155, 14.11.2026)
ALEGERI_CH = (("device", N_("După telecomandă")),
	("zap", N_("Schimbă canalul")), ("list", N_("Deschide lista de canale")))
ALEGERI_PROFIL = {"hds_ch_privire": ALEGERI_CH,
	"hds_asezare_taste": (("obisnuita", N_("Obișnuită")), ("neutrino", N_("Felul Neutrino")),
		("neutrino_buchete", N_("Felul Neutrino cu buchete"))),
	"hds_exit_privire": (("hide", N_("Ascunde bara de informații")), ("arata", N_("Arată bara când nu e nimic pe ecran"))),
	"hds_exit_film": (("hide", N_("Ascunde bara de informații")), ("ask", N_("Ask user")),
		("movielist", N_("Return to movie list")), ("quit", N_("Return to previous service"))),
	# up: dintr-un buchet sau dosar EXIT urca un nivel, iar in lista de sus inchide lista (ca pana acum); close: EXIT
	# inchide lista direct, din orice nivel, ca in OE-Alliance (urcarea ramane pe tasta 0)
	"hds_exit_lista": (("up", N_("Înapoi un nivel")), ("close", N_("Închide lista"))),
	# mouse-ul: numai texte care exista deja (volumul, meniul, inapoi, sunetul oprit, nimic)
	"hds_mouse_rotita": (("volum", N_("Volumul")), ("obisnuit", N_("Funcția obișnuită"))),
	"hds_mouse_mijloc": (("meniu", N_("Meniu")), ("mut", N_("Sunet oprit")), ("inapoi", N_("Înapoi")), ("nimic", N_("Nimic"))),
	"hds_mouse_spate": (("inapoi", N_("Înapoi")), ("mut", N_("Sunet oprit")), ("meniu", N_("Meniu")), ("nimic", N_("Nimic"))),
	"hds_mouse_fata": (("mut", N_("Sunet oprit")), ("inapoi", N_("Înapoi")), ("meniu", N_("Meniu")), ("nimic", N_("Nimic")))}

# KEY1 (tamiciav7): cat se tine tasta pentru randurile de apasare lunga; apasarea lunga vine dupa 4 repetari
# (main/enigma.cpp), cam o secunda. Acelasi text sub lista din Butoane colorate si in pagina web /taste-rapide.
NOTA_APASARE_LUNGA = _("Apăsare lungă: ține tasta apăsată ~1 s.")

ASEZARE_AJUTOR = _("Felul Neutrino: sus/jos schimbă canalul, stânga/dreapta volumul, OK deschide lista. "
	"Cu buchete: stânga/dreapta deschid lista și apoi schimbă buchetul. Obișnuită readuce setările tale.")


def initConfigProfil(config=None):
	config = _config(config)
	from Components.config import ConfigYesNo, ConfigSelection, ConfigSubsection
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	u = config.usage
	for k, implicit, _text in PROFIL_SETARI:
		# alegerile in limba de acum (la pornire poate inca fara limba; la ecran si in web se traduc din nou)
		alegeri = None if isinstance(implicit, bool) else [(v, _tr(t)) for v, t in ALEGERI_PROFIL[k]]
		if k not in u.content.items:
			setattr(u, k, ConfigYesNo(default=implicit) if alegeri is None
				else ConfigSelection(default=implicit, choices=alegeri))
		elif alegeri is not None:
			getattr(u, k).setChoices(alegeri, default=implicit)   # valoarea aleasa ramane
	return u


def optiune(nume, config=None):
	"""Valoarea curenta sau fabrica, inclusiv inainte de initializarea interfetei."""
	try:
		return getattr(_config(config).usage, nume).value
	except (AttributeError, KeyError, ImportError):
		return dict((k, v) for k, v, _text in PROFIL_SETARI).get(nume)


def asezare_neutrino(config=None):
	"""Un strat peste preferinte: nicio valoare personala nu se rescrie."""
	return optiune("hds_asezare_taste", config) in ("neutrino", "neutrino_buchete")


def schimba_buchet_la_zap(config=None, aplica_asezare=True):
	"""In asezarea Neutrino sagetile raman in buchetul curent."""
	return not (aplica_asezare and asezare_neutrino(config)) and _valoare(config, "usage", "quickzap_bouquet_change", False)


def actiune_asezare(buton, config=None):
	if not asezare_neutrino(config):
		return None
	buchete = optiune("hds_asezare_taste", config) == "neutrino_buchete"
	return {"up_short": "zap_next", "down_short": "zap_previous", "ok_short": "channellist",
		"left_short": "channellist" if buchete else "volume_down",
		"right_short": "channellist" if buchete else "volume_up",
		"channelup_short": "zap_next", "channeldown_short": "zap_previous"}.get(buton)


def actiune_efectiva(buton, config=None, aplica_asezare=True):
	asezare = actiune_asezare(buton, config) if aplica_asezare else None
	if asezare is not None:
		return asezare
	valoare = actiune_aleasa(buton, config)
	return FUNCTII_OBISNUITE.get(buton, "default") if valoare == "default" else valoare


TEXTE_ACTIUNI = {
	"move_up": _("Rândul anterior"), "move_down": _("Rândul următor"),
	"none": _("Nimic"), "default": _("Funcția obișnuită"),
	"hbbtv": _("HbbTV"), "record": _("Înregistrează"),
	"eventinfo": _("Detaliile emisiunii"), "epg_multi": _("Ghidul buchetului curent"),
	"epg_single": _("Ghidul canalului curent"), "epg": _("Alegerea tipului de ghid (EPG)"),
	"epg_grafic": _("Ghid grafic"),
	"subtitle_toggle": _("Pornește sau oprește ultima subtitrare"), "subtitle": _("Lista subtitrărilor"),
	"subservices": _("Subcanale"), "audio": _("Selectare pistă audio"),
	"extensions": _("Lista extensiilor"), "portal": _("Portal"),
	"bouquets": _("Lista buchetelor și favoritelor"), "favourites": _("Favorite"),
	"favorite_toggle": _("Adaugă sau scoate canalul din Favorite"),
	"favorite_choose_bouquet": _("Alege buchetul pentru canal"),
	"select_channel": _("Alege canalul de sub cursor"), "search_channels": _("Caută canale"),
	"toggle_layout": _("Listă sau dale"), "search_settings": _("Caută în meniu"),
	"menu_options": _("Opțiunile ecranului"), "edit_value": _("Selectează sau schimbă valoarea"),
	"choose_value": _("Lista valorilor setării"), "save": _("Save"), "cancel": _("Cancel"),
	"back_unsaved": _("Înapoi, cu verificarea modificărilor"),
	"move_recording": _("Mută"), "sort_recordings": _("Sortare"),
	"delete_recording": _("Șterge, cu confirmare"), "recording_location": _("Alt dosar"),
	"tags_or_menu": _("Etichete sau meniu"), "movie_stop": _("Oprește filmul după preferința aleasă"),
	"movie_exit": _("Ieșire din film după preferința aleasă"),
	"movielist": _("Înapoi la lista de filme"), "ask": _("Ask user"),
	"quit": _("Return to previous service"), "previous_channel": _("Canalul anterior"),
	"bookmark": _("Marcaj în film"), "pause": _("Pauză"), "play": _("Redare"),
	"stop_timeshift": _("Oprește timeshift"), "timeshift": _("Pornește timeshift"),
	"teletext": _("Teletext"), "help": _("Tastele acestui ecran"),
	"standby": _("Standby"), "shutdown_menu": _("Meniul de oprire"),
	"pip_close": _("Oprește PiP"), "hide": _("Ascunde bara de informații"),
	"exit_arata": _("Arată bara când nu e nimic pe ecran"),
	"next_bouquet": _("Buchetul următor"), "previous_bouquet": _("Buchetul anterior"),
	"page_up": _("Pagina anterioară"), "page_down": _("Pagina următoare"),
	"list_tv": _("Lista de canale TV"), "list_radio": _("Lista de canale radio"),
	"zap_next": _("Canalul următor"), "zap_previous": _("Canalul anterior"),
	"volume_down": _("Mai încet"), "volume_up": _("Mai tare"),
	"radio_equalizer": _("Egalizator"), "radio_visualizer": _("Vizualizatorul următor"),
	"radio_palette": _("Culorile următoare"),
	"epg_previous": _("Emisiunile anterioare"), "epg_next": _("Emisiunile următoare"),
	"epg_timer": _("Adaugă sau șterge programarea"), "epg_zap": _("Pornește canalul ales"),
	"back": _("Înapoi"),
	"channel_history": _("Canale recente"),
	"mozaic": _("Mozaic: toate canalele transponderului"),
	"infobar_fixed": _("Bara de informații fixă (a doua apăsare o ascunde)"),
	"vpn": _("VPN"),
	"my_key_profiles": _("Profilurile mele"), "key_defaults": _("Valori implicite"),
}

# EXIT in lista de canale (sens_tasta, alegerea hds_exit_lista): aceleasi texte ca alegerile setarii
TEXTE_ACTIUNI["back_level"] = _("Înapoi un nivel")
TEXTE_ACTIUNI["close_list"] = _("Închide lista")


def text_actiune(actiune):
	if actiune.startswith("plugin:"):
		p = pluginuri_alocabile().get(actiune)
		return _tr(N_("Plugin: %s")) % p.name if p else _tr(N_("Plugin indisponibil (%s)")) % actiune[-8:]
	return _tr(TEXTE_ACTIUNI.get(actiune, dict(ACTIUNI_DISPONIBILE).get(actiune, actiune)))


# Actiunile care se repeta cat tii tasta (faza "r"), ca tastele VOL. Canalul se schimba o data pe apasare.
ACTIUNI_REPETATE = ("volume_up", "volume_down")


def _valoare(config, sectiune, nume, implicit):
	try:
		return getattr(getattr(_config(config), sectiune), nume).value
	except (AttributeError, KeyError, ImportError):
		return implicit


def sens_tasta(context, key, lung=False, config=None, **stare):
	"""Sensul folosit de executie, editor, web si ajutor. key este numele fizic."""
	if key == "help":
		return "none" if lung else "help"
	if key == "power":
		x = _valoare(config, "usage", "on_long_powerpress" if lung else "on_short_powerpress",
			"show_menu" if lung else "standby")
		return "shutdown_menu" if x == "show_menu" else x
	if context in ("live", "radio", "timeshift"):
		if key == "red" and stare.get("hbbtv"):
			return "none" if lung else "hbbtv"
		if context == "radio" and _valoare(config, "hds_radio", "taste_colorate", False):
			r = {"green": "radio_equalizer", "yellow": "radio_visualizer", "blue": "radio_palette"}
			if key in r:
				return "none" if lung else r[key]
		if key.startswith("number_"):
			if key == "number_0" and (not lung or context == "timeshift"):
				return "bookmark" if context == "timeshift" else "previous_channel"
			if context == "timeshift":
				return "default"
		setting = next((x[2 if lung else 1] for x in LEGATURI_TASTE if x[0] == key), None)
		if setting:
			# Timeshift pastreaza tastele derularii, inclusiv alocarile manuale.
			if context == "timeshift":
				a = actiune_aleasa(setting, config)
				if a == "default":
					a = FUNCTII_OBISNUITE.get(setting, "default")
			else:
				a = actiune_efectiva(setting, config)
			if a != "default":
				return a
		if lung:
			return "favorite_toggle" if key == "fav" else "none"
		if key in ("up", "down"):
			from Components.HdsSageti import ce_face
			v = _valoare(config, "usage", "hds_sageata_sus", "current")
			f = ce_face(v, key == "up")
			if f == "current":
				f = "radio" if context == "radio" else "tv"
			if f in ("tv", "radio"):
				return "list_" + f
			return "zap_next" if (key == "up") == (f == "zap") else "zap_previous"
		if key in ("channelup", "channeldown"):
			v = optiune("hds_ch_privire", config)
			if v == "list" or (v == "device" and "advanced remote control" not in
				stare.get("device", "dreambox advanced remote control (native)")):
				return "channellist"
			return "zap_next" if key == "channelup" else "zap_previous"
		if key in ("left", "right"):
			if _valoare(config, "usage", "hds_stanga_dreapta_privire", "actual") == "volum":
				return "volume_up" if key == "right" else "volume_down"
			return "zap_next" if key == "right" else "zap_previous"
		return {"red": "default", "fav": "bouquets", "text": "teletext", "audio": "audio",
			"exit": "pip_close" if stare.get("pip") else ("exit_arata" if optiune("hds_exit_privire", config) == "arata" else "hide"),
			"play": "play",
			"pause": "pause" if context == "timeshift" else "timeshift",
			"stop": "stop_timeshift", "portal": "portal", "menu": "menu"}.get(key, "default")
	if context == "channel_list":
		if not lung and asezare_neutrino(config):
			laterale = ("previous_bouquet", "next_bouquet") if optiune("hds_asezare_taste", config) == "neutrino_buchete" else ("page_up", "page_down")
			actiune = {"up": "move_up", "down": "move_down", "left": laterale[0], "right": laterale[1],
				"exit": "close_list"}.get(key)
			if actiune:
				return actiune
		if key == "fav":
			return "favorite_choose_bouquet" if lung else (
				"favorite_toggle" if optiune("hds_fav_scurt_adauga", config) else "bouquets")
		if key == "ok":
			return ("search_channels" if optiune("hds_ok_lung_cauta", config) else "none") if lung else "select_channel"
		if lung:
			return "none"
		return {"text": "search_channels" if optiune("hds_text_lista_cauta", config) else "none",
			"channelup": "next_bouquet", "channeldown": "previous_bouquet",
			# EXIT: Screens/ChannelSelection.hdsTastaExit (in mutare si in editare EXIT termina numai mutarea/editarea)
			"exit": "close_list" if optiune("hds_exit_lista", config) == "close" else "back_level"}.get(key, "default")
	if context == "movie_list":
		if lung:
			return "none"
		vechi = optiune("hds_filme_culori_vechi", config)
		return {"red": "delete_recording", "green": "sort_recordings" if vechi else "move_recording",
			"yellow": "recording_location", "blue": "tags_or_menu" if vechi else "sort_recordings"}.get(key, "default")
	if context == "movie":
		if key == "subtitle":
			return actiune_efectiva("subtitle_long" if lung else "subtitle_short", config)
		if lung:
			return "none"
		return {"stop": _valoare(config, "usage", "on_movie_stop", "movielist"),
			"exit": optiune("hds_exit_film", config), "number_0": "bookmark", "audio": "audio", "text": "teletext",
			"pause": "pause", "play": "play"}.get(key, "default")
	if context == "epg":
		if lung:
			return "none"
		multi = stare.get("epg_multi", True)
		return {"ok": "eventinfo", "info": "eventinfo", "green": "epg_timer",
			"red": "epg_zap" if multi else "none",
			"yellow": "epg_previous" if multi else "sort_recordings",
			"blue": "epg_next" if multi else "none", "exit": "back",
			"channelup": "next_bouquet" if multi else "none",
			"channeldown": "previous_bouquet" if multi else "none"}.get(key, "default")
	if lung:
		return "none"
	if context == "button_setup":
		return {"yellow": "key_defaults", "blue": "my_key_profiles"}.get(key,
			sens_tasta("setup", key, config=config, **stare))
	if context == "setup":
		return {"red": "cancel", "green": "save", "exit": "back_unsaved", "ok": "edit_value",
			"menu": "choose_value", "channelup": "page_up", "channeldown": "page_down"}.get(key, "default")
	if context == "menu":
		return {"menu": "menu_options",
			"yellow": "toggle_layout" if optiune("hds_meniu_galben_aspect", config) else "none",
			"text": "search_settings" if optiune("hds_meniu_text_cauta", config) else "none",
			"channelup": "page_up", "channeldown": "page_down"}.get(key, "default")
	return "default"


TASTE_PROFIL = ("up", "down", "left", "right", "ok", "fav", "info", "epg", "red", "green", "yellow",
	"blue", "audio", "subtitle", "text", "channelup", "channeldown", "play", "pause", "stop", "number_0",
	"exit", "menu", "portal", "help", "power")

ETICHETE_TASTE = {"up": _("SUS"), "down": _("JOS"), "left": _("STÂNGA"), "right": _("DREAPTA"),
	"red": _("ROȘU"), "green": _("VERDE"), "yellow": _("GALBEN"), "blue": _("ALBASTRU"),
	"channelup": "CH+", "channeldown": "CH-", "number_0": "0"}


def profil_context(context, config=None, **stare):
	rez = []
	for key in TASTE_PROFIL:
		a, b = [sens_tasta(context, key, lung=l, config=config, **stare) for l in (False, True)]
		rez.append({"key": key, "short": a, "long": b,
			"text_short": text_actiune(a), "text_long": text_actiune(b)})
	return rez


CONTEXTE_ECRANE = {
	"InfoBar": "live", "HdsEcranRadio": "radio", "HdsEcranRadioSetari": "setup",
	"ChannelSelection": "channel_list", "ChannelSelectionRadio": "channel_list",
	"HdsListaCanaleRadio": "channel_list", "MovieSelection": "movie_list", "MoviePlayer": "movie",
	"Menu": "menu", "MainMenu": "menu", "Setup": "setup", "HdsButtonSetup": "button_setup",
	"EPGSelection": "epg", "SecondInfoBar": "technical",
	"ConfigListScreen": "setup", "HdsEcranRadioOdihna": "radio",
}


def context_ecran(dialog):
	for clasa in type(dialog).__mro__:
		context = CONTEXTE_ECRANE.get(clasa.__name__)
		if context is not None:
			if context == "live":
				if getattr(dialog, "timeshift_enabled", False):
					return "timeshift"
				radio = getattr(dialog, "hdsRadio", None)
				if getattr(radio, "radio", False) or getattr(getattr(dialog, "servicelist", None), "mode", None) == 1:
					return "radio"
			return context
	return None


def taste_ajutor(context, config=None, **stare):
	"""Aceleasi descrieri scurt/lung pe prima pagina HELP si in web."""
	rez = []
	for row in profil_context(context, config, **stare):
		key = ETICHETE_TASTE.get(row["key"], row["key"].upper())
		if row["short"] != "default":
			rez.append([key, row["text_short"], -1])
		elif row["key"] == "red" and context in ("live", "radio", "timeshift"):
			rez.append([key, _("HbbTV când aplicația canalului este disponibilă; altfel funcția obișnuită a telecomenzii."), -1])
		are_scurta = row["short"] != "default" or (row["key"] == "red" and context in ("live", "radio", "timeshift"))
		if are_scurta and row["long"] != "default" and row["key"] in ("info", "epg", "subtitle", "red", "green", "yellow", "blue", "fav", "ok", "power", "menu"):
			rez.append([key + " " + _("(apăsare lungă)"), row["text_long"], -1])
	if context == "live":
		# < tinut apasat (lista canalelor recente, Screens/HdsIstoricCanale.py): < nu e in TASTE_PROFIL (profilele), deci
		# randul de ajutor se pune aici, numai pe bara
		lunga = actiune_efectiva("previous_long", config)
		if lunga not in ("default", "none"):
			rez.append(["< " + _("(apăsare lungă)"), text_actiune(lunga), -1])
	return rez


def config_fabrica():
	"""Profilul documentatiei citite pe PC, fara initializarea receptorului."""
	class Valori(object):
		pass
	c, b = Valori(), Valori()
	c.content = Valori()
	c.content.items = {"hds_buttons": b}
	c.hds_buttons = b
	b.content = Valori()
	b.content.items = {}
	for k, v in VALORI_IMPLICITE.items():
		el = Valori()
		el.value = v
		setattr(b, k, el)
		b.content.items[k] = el
	c.usage = Valori()
	return c


# id(config) -> subsectiunea hds_buttons gasita completa. Pagina web (/api/statusinfo, profilTaste) cheama functia de
# ~30 de ori la fiecare cerere, la cateva secunde cat panoul e deschis; verificarea celor ~50 de chei costa ~1 ms pe
# Octagon SF8008 de fiecare data (masurat in proces). Se crede numai cat config are tot aceeasi subsectiune.
_COMPLETE = {}


def initConfigButtonSetup(config=None):
	# Verificam dictionarul: unele versiuni de ConfigSubsection arunca KeyError.
	config = _config(config)
	b = _COMPLETE.get(id(config))
	if b is not None and config.content.items.get("hds_buttons") is b:
		return b
	chei = [k for k, _text in SCURTE + BUTOANE]
	if "hds_buttons" in config.content.items:
		b = config.hds_buttons
		cunoscute = getattr(getattr(b, "content", None), "items", vars(b))
		if all(k in cunoscute for k in chei):
			if config.content.items.get("hds_buttons") is b:
				_COMPLETE[id(config)] = b
			return b
	from Components.config import ConfigSubsection, ConfigSelection
	if "hds_buttons" not in config.content.items:
		config.hds_buttons = ConfigSubsection()
	b = config.hds_buttons
	for cheie, _text in SCURTE + BUTOANE:
		if cheie not in b.content.items:
			# Alegerea unui plugin lipsa trebuie pastrata si la pornire.
			veche = b.content.stored_values.get(cheie, "")
			alegeri = _cu_indisponibile(ACTIUNI_DISPONIBILE, [veche])
			setattr(b, cheie, ConfigSelection(
				default=VALORI_IMPLICITE[cheie], choices=alegeri))
	return b


def pluginuri_alocabile(pluginuri=None):
	"""Identificatori fara pozitia pluginului in inventar."""
	from hashlib import sha256
	if pluginuri is None:
		from Components.PluginComponent import plugins
		pluginuri = plugins.pluginuriDeDeschis()
	grupe = {}
	for p in pluginuri:
		f = p.fnc
		f = getattr(f, "func", f)
		cale = (p.path or "").replace("\\", "/").split("/Plugins/")[-1]
		ident = "\n".join((cale, getattr(f, "__module__", ""),
			getattr(f, "__qualname__", getattr(f, "__name__", ""))))
		grupe.setdefault(ident, []).append(p)
	rez = {}
	ambigue = set()
	for ident, grupa in grupe.items():
		for p in grupa:
			# Unele pluginuri expun mai multe actiuni prin aceeasi functie.
			# Numai acolo folosim si eticheta, ca fiecare sa poata fi aleasa.
			text = ident if len(grupa) == 1 else ident + "\n" + str(p.name)
			cheie = "plugin:" + sha256(text.encode("utf-8")).hexdigest()
			if cheie in rez and rez[cheie] != p:
				ambigue.add(cheie)
			rez[cheie] = p
	# Nu pornim alt plugin daca doi descriptori au aceeasi identitate.
	return dict((k, p) for k, p in rez.items() if k not in ambigue)


def _cu_indisponibile(alegeri, valori):
	rez = list(alegeri)
	for v in valori:
		if v.startswith("plugin:") and v not in dict(rez):
			rez.append((v, _("Plugin indisponibil (%s)") % v[-8:]))
	return rez


def actualizeaza_alegeri(config=None, pluginuri=None):
	"""La deschiderea ecranului sau paginii, cu inventarul instalat acum."""
	b = initConfigButtonSetup(config)
	lista = pluginuri_alocabile(pluginuri)
	# traduse acum: lista s-a facut la import, uneori inainte de limba aleasa (ar fi ramas in romana)
	alegeri = [(k, _tr(text)) for k, text in ACTIUNI_DISPONIBILE] + [
		(k, _tr(N_("Plugin: %s")) % p.name) for k, p in sorted(
			lista.items(), key=lambda x: (str(x[1].name).lower(), x[0]))]
	alegeri = _cu_indisponibile(alegeri,
		[getattr(b, k).value for k, _text in SCURTE + BUTOANE])
	for k, _text in SCURTE + BUTOANE:
		getattr(b, k).setChoices(alegeri, default=VALORI_IMPLICITE[k])
	return b


def salveaza(config=None):
	"""Aceeasi salvare pe televizor si in web."""
	b = initConfigButtonSetup(config)
	for cheie, _text in BUTOANE + SCURTE:
		getattr(b, cheie).save()


# Profilurile sunt copii ale setarilor existente, fara un strat nou de alocare.
CALE_PROFILURI = "/etc/enigma2/hds-taste-profiluri.json"
MAX_PROFILURI = 100
MAX_PROFIL = 64 * 1024
USAGE_TASTE = ("hds_sageata_sus", "hds_ok_privire", "hds_stanga_dreapta_privire",
	"quickzap_bouquet_change", "on_short_powerpress", "on_long_powerpress", "on_movie_stop", "pip_zero_button")


def _nume_profil(nume):
	if not isinstance(nume, str) or len(nume.strip()) > 64 or any(ord(c) < 32 or ord(c) == 127 or 0xd800 <= ord(c) <= 0xdfff for c in nume):
		raise ValueError(_tr(N_("Numele profilului poate avea cel mult 64 de caractere, fără caractere de control.")))
	return nume.strip()


def _elemente_profil(config=None):
	c = _config(config)
	b = initConfigButtonSetup(c)
	u = initConfigProfil(c)
	rez = {"buttons": {k: getattr(b, k) for k, _text in SCURTE + BUTOANE},
		"usage": {k: getattr(u, k) for k, _v, _text in PROFIL_SETARI}, "radio": {}}
	for k in USAGE_TASTE:
		if k in u.content.items:
			rez["usage"][k] = getattr(u, k)
	if "hds_radio" in c.content.items and "taste_colorate" in c.hds_radio.content.items:
		rez["radio"]["taste_colorate"] = c.hds_radio.taste_colorate
	return rez


def poza_profil(nume, config=None):
	p = {"format": "hds-taste", "version": 1, "name": _nume_profil(nume)}
	for grup, elemente in _elemente_profil(config).items():
		p[grup] = {k: el.value for k, el in elemente.items()}
	return p


def verifica_profil(p):
	"""Valideaza tot profilul inainte de schimbarea setarilor sau fisierului omului."""
	import re
	if not isinstance(p, dict) or p.get("format") != "hds-taste":
		raise ValueError(_tr(N_("Fișierul nu este un profil de taste HD Satelit.")))
	if type(p.get("version")) is not int or p["version"] != 1:
		raise ValueError(_tr(N_("Versiunea profilului nu este acceptată. Actualizează imaginea și încearcă din nou.")))
	if set(p) != {"format", "version", "name", "buttons", "usage", "radio"}:
		raise ValueError(_tr(N_("Profilul este incomplet sau conține date necunoscute.")))
	_nume_profil(p["name"])
	if not p.get("buttons") or not isinstance(p.get("usage"), dict) or "hds_asezare_taste" not in p["usage"]:
		raise ValueError(_tr(N_("Profilul este incomplet sau conține date necunoscute.")))
	for grup in ("buttons", "usage", "radio"):
		if not isinstance(p[grup], dict) or len(p[grup]) > 128:
			raise ValueError(_tr(N_("Profilul conține o listă de taste nevalidă.")))
		for k, v in p[grup].items():
			if not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", k):
				raise ValueError(_tr(N_("Profilul conține o tastă nevalidă.")))
			if type(v) not in (str, bool) or (isinstance(v, str) and len(v) > 128):
				raise ValueError(_tr(N_("Profilul conține o valoare nevalidă.")))
	for k, v in p["buttons"].items():
		if not isinstance(v, str) or (v not in dict(ACTIUNI_DISPONIBILE) and not re.fullmatch(r"plugin:[0-9a-f]{64}", v)):
			raise ValueError(_tr(N_("Profilul conține o acțiune necunoscută.")))
	# Valideaza si setarile cunoscute care lipsesc de pe receptorul de aici.
	choices = dict(ALEGERI_PROFIL)
	choices.update(hds_sageata_sus=[(v, v) for v in ("current", "radio", "tv_radio", "tv", "radio_radio", "zap", "zap_invers")],
		hds_ok_privire=[(v, v) for v in ("bara", "lista")],
		hds_stanga_dreapta_privire=[(v, v) for v in ("actual", "volum")],
		on_short_powerpress=[(v, v) for v in ("standby", "show_menu", "shutdown")],
		on_long_powerpress=[(v, v) for v in ("standby", "show_menu", "shutdown")],
		on_movie_stop=[(v, v) for v in ("ask", "movielist", "quit")],
		pip_zero_button=[(v, v) for v in ("standard", "swap", "swapstop", "stop")])
	booleans = {k for k, v, _text in PROFIL_SETARI if isinstance(v, bool)} | {"quickzap_bouquet_change"}
	for k, v in p["usage"].items():
		if (k in booleans and type(v) is bool) or (k in choices and isinstance(v, str) and v in dict(choices[k])):
			continue
		raise ValueError(_tr(N_("Profilul conține o setare de taste necunoscută sau nevalidă.")))
	if any(k != "taste_colorate" or type(v) is not bool for k, v in p["radio"].items()):
		raise ValueError(_tr(N_("Profilul conține o setare radio nevalidă.")))
	return p


def _json_profil(text):
	import json
	def perechi(lista):
		rez = {}
		for k, v in lista:
			if k in rez:
				raise ValueError()
			rez[k] = v
		return rez
	try:
		return json.loads(text, object_pairs_hook=perechi)
	except (ValueError, UnicodeError, RecursionError):
		raise ValueError(_tr(N_("Fișierul de profil este stricat. Tastele au rămas neschimbate.")))


def citeste_profiluri():
	import os
	import stat
	try:
		if os.path.islink(CALE_PROFILURI):
			raise ValueError(_tr(N_("Fișierul profilurilor nu poate fi o legătură.")))
		fd = os.open(CALE_PROFILURI, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
		with os.fdopen(fd, "rb") as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise ValueError(_tr(N_("Fișierul profilurilor nu este un fișier obișnuit.")))
			text = f.read(MAX_PROFILURI * MAX_PROFIL + 1)
	except FileNotFoundError:
		return []
	if len(text) > MAX_PROFILURI * MAX_PROFIL:
		raise ValueError(_tr(N_("Fișierul profilurilor este prea mare.")))
	d = _json_profil(text)
	if not isinstance(d, dict) or d.get("format") != "hds-taste-lista" or type(d.get("version")) is not int or d["version"] != 1:
		raise ValueError(_tr(N_("Fișierul profilurilor este stricat sau are o versiune neacceptată.")))
	lista = d.get("profiles")
	if not isinstance(lista, list) or len(lista) > MAX_PROFILURI:
		raise ValueError(_tr(N_("Lista profilurilor nu este validă.")))
	ids = set()
	for x in lista:
		if not isinstance(x, dict) or set(x) != {"id", "profile"} or not isinstance(x["id"], str) or len(x["id"]) != 32 or any(c not in "0123456789abcdef" for c in x["id"]) or x["id"] in ids:
			raise ValueError(_tr(N_("Lista profilurilor nu este validă.")))
		ids.add(x["id"])
		verifica_profil(x["profile"])
	return lista


def _scrie_profiluri(lista):
	import json
	import os
	import tempfile
	dosar = os.path.dirname(CALE_PROFILURI)
	fd, temporar = tempfile.mkstemp(prefix=".hds-taste-", suffix=".nou", dir=dosar)
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			json.dump({"format": "hds-taste-lista", "version": 1, "profiles": lista}, f, ensure_ascii=False, indent=2)
			f.flush()
			os.fsync(f.fileno())
		os.replace(temporar, CALE_PROFILURI)
		# Pastreaza redenumirea pe sistemele de fisiere care permit fsync pe dosar.
		try:
			d = os.open(dosar, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
			try:
				os.fsync(d)
			finally:
				os.close(d)
		except OSError:
			pass
	finally:
		if os.path.exists(temporar):
			os.unlink(temporar)


def _adauga_profil(p):
	from copy import deepcopy
	from uuid import uuid4
	p = deepcopy(verifica_profil(p))
	p["name"] = _nume_profil(p["name"])
	lista = citeste_profiluri()
	if len(lista) >= MAX_PROFILURI:
		raise ValueError(_tr(N_("Ai deja 100 de profiluri. Șterge unul pentru a salva altul.")))
	if not p["name"]:
		nume = {x["profile"]["name"] for x in lista}
		n = 1
		while _tr(N_("Profilul meu %d")) % n in nume:
			n += 1
		p["name"] = _tr(N_("Profilul meu %d")) % n
	x = {"id": uuid4().hex, "profile": verifica_profil(p)}
	lista.append(x)
	_scrie_profiluri(lista)
	return x


def salveaza_profil(nume="", config=None):
	return _adauga_profil(poza_profil(nume, config))


def importa_profil(text, config=None):
	if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_PROFIL:
		raise ValueError(_tr(N_("Profilul este prea mare (maximum 64 KiB).")))
	return _adauga_profil(verifica_profil(_json_profil(text)))


def gaseste_profil(ident):
	for x in citeste_profiluri():
		if x["id"] == ident:
			return x["profile"]
	raise ValueError(_tr(N_("Profilul ales nu mai există.")))


def sterge_profil(ident):
	lista = citeste_profiluri()
	noi = [x for x in lista if x["id"] != ident]
	if len(noi) == len(lista):
		raise ValueError(_tr(N_("Profilul ales nu mai există.")))
	_scrie_profiluri(noi)


def redenumeste_profil(ident, nume):
	nume = _nume_profil(nume)
	if not nume:
		raise ValueError(_tr(N_("Scrie numele nou al profilului.")))
	lista = citeste_profiluri()
	for x in lista:
		if x["id"] == ident:
			x["profile"]["name"] = nume
			_scrie_profiluri(lista)
			return
	raise ValueError(_tr(N_("Profilul ales nu mai există.")))


# Only plain data crosses the worker boundary. Deferred callbacks run on Enigma2.
_PROFIL_OCUPAT = False


class EroareSalvareTaste(OSError):
	pass


def profil_ocupat():
	return _PROFIL_OCUPAT


# Main owns the job list and Deferreds; workers only handle plain data.
_LUCRARI_PROFIL = []
_EXECUTOR_PROFIL = None
_IESIRE_PROFIL = False


def pe_fir_profil(functie, *args):
	from concurrent.futures import ThreadPoolExecutor
	from twisted.internet import reactor
	from twisted.internet.defer import Deferred, fail
	from twisted.python.failure import Failure
	global _EXECUTOR_PROFIL
	class LucruDisc(Deferred):
		def cancel(self):
			# Disk IO cannot be interrupted. Keep the reservation until it returns.
			pass
	rez = LucruDisc()
	try:
		if _EXECUTOR_PROFIL is None:
			_EXECUTOR_PROFIL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hds-taste")
		viitor = _EXECUTOR_PROFIL.submit(functie, *args)
	except Exception:
		eroare = Failure()
		executor, _EXECUTOR_PROFIL = _EXECUTOR_PROFIL, None
		if executor is not None:
			# Thread.start can fail after submit queued the write. Cancel it too.
			try:
				executor.shutdown(wait=False, cancel_futures=True)
			except Exception:
				pass
		return fail(eroare)
	def livreaza():
		# Also callable after the event loop, exactly once and always on main.
		if lucrare not in _LUCRARI_PROFIL:
			return
		_LUCRARI_PROFIL.remove(lucrare)
		try:
			date = viitor.result()
		except Exception:
			date = Failure()
		rez.callback(date)
	lucrare = (viitor, livreaza)
	_LUCRARI_PROFIL.append(lucrare)
	viitor.add_done_callback(lambda _f: reactor.callFromThread(livreaza))
	return rez


def termina_la_iesire():
	"""After the native loop: finish only our jobs, without running other events."""
	from concurrent.futures import wait
	global _IESIRE_PROFIL, _EXECUTOR_PROFIL
	_IESIRE_PROFIL = True
	while _LUCRARI_PROFIL:
		viitor, livreaza = _LUCRARI_PROFIL[0]
		wait([viitor])
		livreaza()
	if _EXECUTOR_PROFIL is not None:
		_EXECUTOR_PROFIL.shutdown(wait=True)
		_EXECUTOR_PROFIL = None


def _exclusiv_profil(functie):
	from twisted.internet.defer import fail, maybeDeferred
	global _PROFIL_OCUPAT
	if _PROFIL_OCUPAT or _IESIRE_PROFIL:
		return fail(ValueError(_tr(N_("Se lucrează la un profil. Încearcă din nou după terminare."))))
	_PROFIL_OCUPAT = True
	def liber(rez):
		global _PROFIL_OCUPAT
		_PROFIL_OCUPAT = False
		return rez
	return maybeDeferred(functie).addBoth(liber)


def _capabilitati_taste(dispozitive, legaturi):
	import os
	from fcntl import ioctl
	from Components.InputDevice import EVIOCGBIT
	coduri = set()
	citit = False
	for dev in dispozitive:
		try:
			fd = os.open("/dev/input/" + dev, os.O_RDONLY | os.O_NONBLOCK)
			try:
				b = ioctl(fd, EVIOCGBIT(1, 96), bytes(96))
			finally:
				os.close(fd)
			if any(b):
				citit = True
				coduri.update(n for n in range(len(b) * 8) if b[n // 8] & (1 << (n % 8)))
		except OSError:
			continue
	return {key for key, taste in legaturi.items() if taste & coduri} if citit else None


def taste_disponibile():
	"""Snapshot input objects on main; query device capabilities on a worker."""
	from twisted.internet.defer import succeed
	try:
		from Components.InputDevice import iInputDevices
		from Tools.KeyBindings import queryKeyBinding
		legaturi = {key: {cod for cod, _flags in queryKeyBinding("HdsAlocareTasteActions", key + "_m")}
			for key, _short, _long, _release in LEGATURI_TASTE}
		dispozitive = [dev for dev, info in iInputDevices.Devices.items()
			if info.get("type") == "remote" and dev.startswith("event") and dev[5:].isdigit()]
		if any(legaturi.values()):
			return pe_fir_profil(_capabilitati_taste, dispozitive, legaturi)
	except (ImportError, AttributeError):
		pass
	return succeed(None)


def _scrie_setari_profil(cale, schimbari):
	"""Only plain bytes: unique staging file, merge latest settings, verified result."""
	import os
	import tempfile
	from Components.config import _scrieSigur, _octetiSetari
	cale = os.path.realpath(cale)
	def citeste():
		try:
			with open(cale, "rb") as f:
				return f.read()
		except FileNotFoundError:
			return b""
	for _incercare in range(4):
		baza = citeste()
		vechi = baza.decode("utf-8", "surrogateescape")
		anterior = {k: None for k in schimbari}
		for rand in vechi.splitlines():
			k, separator, v = rand.partition("=")
			if separator and k in anterior:
				anterior[k] = v
		# Keep unrelated lines and unrecognised settings byte for byte.
		randuri = [r for r in vechi.splitlines(keepends=True) if r.split("=", 1)[0] not in schimbari]
		if randuri and not randuri[-1].endswith("\n"):
			randuri[-1] += "\n"
		randuri += [k + "=" + v + "\n" for k, v in schimbari.items() if v is not None]
		date = _octetiSetari("".join(randuri))
		fd, temporar = tempfile.mkstemp(prefix=".hds-taste-setari-", suffix=".nou", dir=os.path.dirname(cale))
		os.close(fd)
		try:
			try:
				st = os.stat(cale)
			except FileNotFoundError:
				st = None
			if st is not None:
				os.chmod(temporar, st.st_mode & 0o7777)
				if hasattr(os, "chown"):
					os.chown(temporar, st.st_uid, st.st_gid)
			# Use the existing byte writer without sharing settings.nou with other saves.
			if not _scrieSigur(temporar, date):
				raise EroareSalvareTaste(_tr(N_("Nu pot salva tastele pe disc. Tastele au rămas neschimbate.")))
			with open(temporar, "rb") as f:
				if f.read() != date:
					raise EroareSalvareTaste(_tr(N_("Salvarea tastelor pe disc nu a putut fi verificată.")))
			if citeste() != baza:
				continue  # Another save completed meanwhile; merge its unrelated keys too.
			os.replace(temporar, cale)
			try:
				d = os.open(os.path.dirname(cale), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
				try:
					os.fsync(d)
				finally:
					os.close(d)
			except OSError:
				pass
			if citeste() != date:
				raise EroareSalvareTaste(_tr(N_("Salvarea tastelor pe disc nu a putut fi verificată.")))
			return anterior
		finally:
			if os.path.exists(temporar):
				os.unlink(temporar)
	raise EroareSalvareTaste(_tr(N_("Setările se schimbă acum. Încearcă din nou după terminare.")))


def _aplica_profil(p, config, configfile, disponibile):
	verifica_profil(p)
	elemente = _elemente_profil(config)
	fizice = {setting: key for key, short, long, _r in LEGATURI_TASTE for setting in (short, long) if setting}
	noi = []
	sarite = 0
	schimbari = {}
	for grup in ("buttons", "usage", "radio"):
		for k, v in p[grup].items():
			if k not in elemente[grup] or (grup == "buttons" and disponibile is not None and fizice.get(k) not in disponibile):
				sarite += 1
				continue
			el = elemente[grup][k]
			if grup != "buttons" and hasattr(el, "choices") and v not in el.choices:
				raise ValueError(_tr(N_("Profilul conține o valoare neacceptată pe acest receptor.")))
			salvat = None if el.save_disabled or (v == el.default and not el.save_forced) else el._hdsInText(v)
			sectiune = {"buttons": "hds_buttons", "usage": "usage", "radio": "hds_radio"}[grup]
			schimbari["config." + sectiune + "." + k] = salvat
			noi.append((el, v))
	# No value or saved flag changes before a verified write. Failure needs no rollback.
	def aplica(anterior):
		campuri = ("_value", "saved_value", "last_value", "default", "choices", "_descr")
		vechi = [(el, {k: getattr(el, k) for k in campuri if hasattr(el, k)}) for el, _v in noi]
		try:
			for el, v in noi:
				if isinstance(v, str) and v.startswith("plugin:") and v not in el.choices:
					el.setChoices(_cu_indisponibile([(a, el.description[a]) for a in el.choices], [v]), default=el.default)
				el.value = v
				el.save()
		except Exception:
			from twisted.python.failure import Failure
			f = Failure()
			# Restore the complete state before notifying. A broken notifier must
			# neither stop healthy notifiers nor prevent the value restoration.
			for el, stare in vechi:
				el.__dict__.update(stare)
			for el, _stare in vechi:
				for notificator in list(el.notifiers):
					try:
						notificator(el)
					except Exception:
						pass
			for el, stare in vechi:
				el.__dict__.update(stare)
			if configfile is not None:
				def esec_revenire(_f):
					raise EroareSalvareTaste(_tr(N_("Tastele au revenit în memorie, dar nu pot confirma revenirea setărilor de pe disc. Încearcă din nou.")))
				return pe_fir_profil(tranzactie.ruleaza, _scrie_setari_profil, configfile.CONFIG_FILE, anterior).addCallbacks(lambda _r: f, esec_revenire)
			return f
		return sarite
	if configfile is None:
		from twisted.internet.defer import succeed
		return succeed(aplica(None))
	from Components.config import TranzactieSetari
	try:
		tranzactie = TranzactieSetari()
	except RuntimeError:
		raise ValueError(_tr(N_("Setările se schimbă acum. Încearcă din nou după terminare.")))
	configfile._scris = None
	def termina(rez):
		from twisted.python.failure import Failure
		error = [None]
		def pas(r=None):
			if isinstance(r, Failure):
				error[0] = r
			configfile._scris = None
			try:
				cereri = tranzactie.preia()
			except Exception:
				tranzactie.inchide(fortat=True)
				return Failure()
			if cereri:
				return pe_fir_profil(tranzactie.termina, cereri).addBoth(pas)
			if tranzactie.inchide():
				return error[0] or rez
			return pas()
		return pas()
	return pe_fir_profil(tranzactie.ruleaza, _scrie_setari_profil, configfile.CONFIG_FILE, schimbari).addCallback(aplica).addBoth(termina)


def aplica_profil(p, config=None, configfile=None, **optiuni):
	from copy import deepcopy
	from twisted.internet.defer import succeed
	p = deepcopy(verifica_profil(p))
	def porneste():
		d = succeed(optiuni["disponibile"]) if "disponibile" in optiuni else taste_disponibile()
		return d.addCallback(lambda disponibile: _aplica_profil(p, config, configfile, disponibile))
	return _exclusiv_profil(porneste)


def operatie_profil(actiune, config=None, configfile=None, ident="", nume="", continut=None):
	"""TV and web share the same worker entry point and mutation guard."""
	from twisted.internet.defer import maybeDeferred
	def porneste():
		if actiune == "lista":
			return pe_fir_profil(citeste_profiluri)
		if actiune == "exporta":
			return pe_fir_profil(gaseste_profil, ident)
		if actiune == "salveaza":
			p = verifica_profil(_json_profil(continut)) if continut is not None else poza_profil(nume, config)
			p["name"] = _nume_profil(nume)
			return pe_fir_profil(_adauga_profil, p)
		if actiune == "importa":
			return pe_fir_profil(importa_profil, continut or "")
		if actiune == "sterge":
			return pe_fir_profil(sterge_profil, ident)
		if actiune == "redenumeste":
			return pe_fir_profil(redenumeste_profil, ident, nume)
		if actiune == "aplica":
			def citit(p):
				return taste_disponibile().addCallback(lambda disponibile: _aplica_profil(p, config, configfile, disponibile))
			return pe_fir_profil(gaseste_profil, ident).addCallback(citit)
		raise ValueError(_tr(N_("Alege ce vrei să faci cu profilul.")))
	return maybeDeferred(porneste) if actiune in ("lista", "exporta") else _exclusiv_profil(porneste)


def actiune_aleasa(buton, config=None):
	"""Valoarea curenta, fara recitirea pluginurilor la fiecare tasta."""
	if buton not in dict(BUTOANE + SCURTE):
		return "none"
	try:
		return getattr(initConfigButtonSetup(config), buton).value
	except (ImportError, AttributeError, KeyError):
		return VALORI_IMPLICITE[buton]


def actiuni_harta(trateaza):
	return dict((tasta + "_" + faza,
		lambda t=tasta, f=faza: trateaza(t, f))
		for tasta, _scurta, _lunga, _elib in LEGATURI_TASTE
		for faza in ("m", "r", "l", "b"))


class AlocareTaste(object):
	"""0 lasa tasta mai departe, 1 o consuma."""

	# Prima repetare poate veni la 280 ms si este filtrata in harta.
	# Lasam loc si urmatoarei repetari, fara a astepta la nesfarsit.
	FARA_SEMN_MS = 650

	def __init__(self, porneste, numar, disponibila, config=None, ceas=None, actiune=None):
		self.porneste = porneste
		self.numar = numar
		self.disponibila = disponibila
		self.config = config
		self.actiune = actiune
		self.lungi = set()
		self.legaturi = dict((x[0], x[1:]) for x in LEGATURI_TASTE)
		self.asteptata = None
		self.incheiate = set()
		self.ceas = ceas
		if ceas is not None:
			ceas.callback.append(self._expira)

	def _opreste_asteptarea(self):
		self.asteptata = None
		if self.ceas is not None:
			self.ceas.stop()

	def anuleaza(self):
		"""Bara a ramas in spatele altui ecran: nicio actiune amanata."""
		if self.asteptata is not None:
			self.incheiate.add(self.asteptata[0])
		self._opreste_asteptarea()
		self.lungi.clear()

	def _asteapta(self):
		if self.ceas is not None:
			self.ceas.start(self.FARA_SEMN_MS, True)

	def _scurta_asteptata(self, motiv):
		if self.asteptata is None:
			return
		tasta, actiune, numeric = self.asteptata
		self._opreste_asteptarea()
		self.incheiate.add(tasta)
		if not self.disponibila(tasta):
			return
		print("[HdsTasteRapide] tasta=%s decizie=scurta motiv=%s" %
			(tasta, motiv))
		if numeric:
			self.numar(int(tasta[7:]))
		else:
			self.porneste(tasta, actiune)

	def _expira(self):
		self._scurta_asteptata("fara semn %d ms" % self.FARA_SEMN_MS)

	def eveniment(self, tasta, faza):
		avea_asteptare = self.asteptata is not None
		if faza == "m":
			# O alta apasare poate ascunde eliberarea celei dinainte.
			self._scurta_asteptata("apasare noua")
			self.incheiate.discard(tasta)
			self.lungi.discard(tasta)
		elif tasta in self.incheiate:
			return 1
		if not self.disponibila(tasta):
			self.anuleaza()
			# Actiunea recuperata poate deschide deja alt ecran.
			# Nu mai chemam hartile vechi cu aceeasi apasare.
			return int(faza == "m" and avea_asteptare)
		scurta, lunga, la_eliberare = self.legaturi[tasta]
		alege = self.actiune or actiune_efectiva
		a = alege(scurta, self.config) if scurta else "default"
		l = alege(lunga, self.config) if lunga else "default"
		if l == "default" and tasta in ("red", "green", "yellow", "blue"):
			l = VALORI_IMPLICITE[tasta]
		proprie = a != "default"
		numeric = tasta.startswith("number_") and l != "default"
		if faza == "m":
			if numeric or (proprie and la_eliberare):
				self.asteptata = (tasta, a, numeric)
				self._asteapta()
				return 1
			if proprie and not la_eliberare:
				self.porneste(tasta, a)
				return 1
			return 0
		if faza == "l":
			if lunga and l != "default":
				# Nimic la culori pastreaza sensul vechi: fara actiune lunga.
				if l == "none":
					self._opreste_asteptarea()
					self.incheiate.add(tasta)
					return 1
				self._opreste_asteptarea()
				self.incheiate.add(tasta)
				self.lungi.add(tasta)
				print("[HdsTasteRapide] tasta=%s semn=l decizie=lunga" % tasta)
				self.porneste(tasta, l)
				return 1
			if proprie and la_eliberare and tasta in ("info", "epg", "subtitle", "audio", "fav"):
				self._opreste_asteptarea()
				self.incheiate.add(tasta)
				self.lungi.add(tasta)
			return int(proprie and not la_eliberare)
		if faza == "b":
			if self.asteptata is not None and self.asteptata[0] == tasta:
				self._scurta_asteptata("eliberare")
				return 1
			if tasta in self.lungi:
				self.lungi.discard(tasta)
				return 1
		if faza == "r" and self.asteptata is not None and self.asteptata[0] == tasta:
			self._asteapta()
		if faza == "r" and proprie and not la_eliberare and a in ACTIUNI_REPETATE:
			# volumul tinut apasat merge mai departe, ca VOL+ si VOL-
			self.porneste(tasta, a)
			return 1
		return int(numeric or proprie)


def cauta_meniu(radacina, id_meniu):
	"""Primul <menu> din tot arborele lui menu.xml (radacina = mdom.getroot()) care are copilul <id val="id_meniu"/>,
	sau None. Nu numai copiii directi ai radacinii: in menu.xml radacina e <menuxml> si toate meniile sunt in meniul
	principal (de aceea POWER lung nu gasea meniul "shutdown" si nu deschidea nimic)."""
	if radacina is None:
		return None
	for meniu in radacina.iter("menu"):
		ident = meniu.find("id")
		if ident is not None and ident.get("val") == id_meniu:
			return meniu
	return None


class ApasareLunga(object):
	"""Apasarea lunga a celor patru butoane colorate, pentru o harta cu trei actiuni pe buton (apasat "m", lung "l",
	eliberat "b"). porneste(buton, actiune) face actiunea si intoarce True; False cand butonul nu e al barei acum
	(aplicatia HbbTV a luat ROSU, ecranul radio ia tastele colorate): atunci totul merge ca pana acum.
	Rezultatele sunt cele ale hartilor (Components/ActionMap.py): 0 = tasta merge mai departe, 1 = oprita aici."""

	def __init__(self, porneste, config=None):
		self.porneste = porneste
		self.config = config
		self.semne = set()

	def apasat(self, buton):
		self.semne.discard(buton)
		return 0

	def lung(self, buton):
		try:
			actiune = actiune_aleasa(buton, self.config)
		except Exception as e:
			print("[HdsTasteRapide] %s lung: setarea nu se poate citi: %s" % (buton, e))
			return 0
		if actiune == "none" or not self.porneste(buton, actiune):
			return 0
		self.semne.add(buton)
		return 1

	def eliberat(self, buton):
		if buton in self.semne:
			self.semne.discard(buton)
			return 1
		return 0


# ---------------------------------------------------------------- lista tastei ALBASTRE, la alegerea omului
# Cererea lui tamiciav7 (LinuxSat 232449 #500990, 22.11.2026): mai multe randuri in lista butonului ALBASTRU (Lista
# extensiilor, Screens/InfoBarGenerics.InfoBarExtensions), cu scurtaturi gata facute (actualizarea softului, informatiile
# de sistem, procesorul, repornirea retelei, testul de viteza) si alegerea omului dintre meniuri, functii si pluginuri.
# Pe televizor: Butoane colorate si taste rapide > Lista butonului albastru (Screens/ButtonSetup.HdsListaAlbastra); in web:
# /lista-albastra (Plugins/Extensions/HdsWebControl/intrari_web.py). Aceeasi logica pentru amandoua, aici.
#
# Doua setari text, goale din fabrica: config.hds_albastru.randuri (randurile puse sau mutate de om, in ordinea lor) si
# config.hds_albastru.ascunse (randurile care se pun singure, scoase de om). Cat amandoua sunt goale, sursa_listei intoarce
# lista neatinsa: ALBASTRU arata exact ce arata si inainte. Identificatorii randurilor:
#   gata:<nume>   scurtaturile gata facute (SCURTATURI_ALBASTRU)
#   m:<entryID>   o intrare sau un grup din menu.xml, ca in Cauta setari (Components/HdsCautaSetari.index)
#   plugin:<..>   un plugin, aceeasi cheie ca la alocarea tastelor (pluginuri_alocabile)
#   tasta:<act>   o functie a tastelor (ACTIUNI_DISPONIBILE, pornita de Screens/InfoBar.hdsFaActiuneaLunga)
#   imagine:<..>  randurile pe care imaginea le pune singura (Acces conditionat, Subcanale, PiP, editorul de marcaje)
# Pluginurile care se inscriu singure in lista extensiilor (WHERE_EXTENSIONSMENU) se pun singure si ele, deci un plugin
# instalat dupa alegere apare tot singur, dupa randurile alese. Un rand ales care nu se poate deschide acum (plugin scos,
# meniu care nu se vede pe nivelul de acum) nu apare in lista, dar ramane in setare.

MAX_RANDURI_ALBASTRU = 60
_ID_ALBASTRU = __import__("re").compile(r"^(gata|m|plugin|tasta|imagine):[A-Za-z0-9_.:-]{1,80}$")

# (identificator, textul randului, intrarea din menu.xml deschisa, SystemInfo cerut)
SCURTATURI_ALBASTRU = (
	("gata:actualizare", N_("Actualizare software"), "m:hds_actualizari", None),
	("gata:informatii", N_("Informații sistem"), "m:info_screen", None),
	("gata:procesor", N_("Procesor: frecvență, încărcare și temperatură"), "m:hds_procesor", "HdsProcesor"),
	("gata:retea", N_("Repornește rețeaua"), None, None),
	("gata:viteza", N_("Testul de viteză al internetului"), None, None),
)

# functiile tastelor care n-au sens intr-o lista: lista insasi, nimic, schimbarea canalului si volumul (tinute apasat),
# "Informatii sistem" (e scurtatura gata:informatii)
_ACTIUNI_FARA_LISTA = ("default", "none", "extensions", "zap_next", "zap_previous", "volume_up", "volume_down", "info")

# randurile imaginii, dupa numele functiei pe care o pornesc (InfoBarGenerics, InfoBar.py)
_RANDURI_IMAGINE = {"hdsAccesConditionat": "imagine:acces", "showPiP": "imagine:pip", "movePiP": "imagine:pip",
	"swapPiP": "imagine:pip", "hdsEditorMarcaje": "imagine:marcaje"}


def initConfigAlbastru(config=None):
	config = _config(config)
	if "hds_albastru" not in config.content.items:
		from Components.config import ConfigSubsection
		config.hds_albastru = ConfigSubsection()
	a = config.hds_albastru
	if "randuri" not in a.content.items:
		from Components.config import ConfigText
		a.randuri = ConfigText(default="", fixed_size=False)
		a.ascunse = ConfigText(default="", fixed_size=False)
	return a


def ids_albastru(text):
	"""Identificatorii dintr-o setare sau dintr-o cerere: bune, fara repetari, cel mult MAX_RANDURI_ALBASTRU."""
	rez = []
	for x in (text or "").split(","):
		x = x.strip()
		if x and x not in rez and _ID_ALBASTRU.match(x):
			rez.append(x)
		if len(rez) >= MAX_RANDURI_ALBASTRU:
			break
	return rez


def alegere_albastru(config=None):
	"""(randuri, ascunse): ce a ales omul; ([], []) din fabrica."""
	a = initConfigAlbastru(config)
	return ids_albastru(a.randuri.value), ids_albastru(a.ascunse.value)


def salveaza_albastru(randuri, ascunse, config=None, configfile=None):
	"""Aceeasi salvare pe televizor si in web, pe loc."""
	a = initConfigAlbastru(config)
	a.randuri.value = ",".join(ids_albastru(",".join(randuri)))
	a.ascunse.value = ",".join(ids_albastru(",".join(ascunse)))
	a.randuri.save()
	a.ascunse.save()
	if configfile is None:
		try:
			from Components.config import configfile
		except ImportError:
			configfile = None
	if configfile is not None:
		configfile.save()


def in_lista_albastra(randuri, ascunse, automate):
	"""Randurile bifate, in ordinea din lista: cele alese de om, apoi cele care se pun singure si n-au fost scoase."""
	return [r for r in randuri if r not in ascunse] + [a for a in automate if a not in ascunse and a not in randuri]


def comuta_albastru(randuri, ascunse, automate, ident):
	"""OK pe un rand (sau bifa din web): (randuri, ascunse) noi. Un rand care se pune singur se ascunde sau se arata din
	nou; celelalte intra la coada randurilor alese sau ies din ele."""
	randuri, ascunse = list(randuri), list(ascunse)
	if ident in in_lista_albastra(randuri, ascunse, automate):
		if ident in randuri:
			randuri.remove(ident)
		if ident in automate and ident not in ascunse:
			ascunse.append(ident)
	else:
		if ident in ascunse:
			ascunse.remove(ident)
		if ident not in automate and ident not in randuri:
			randuri.append(ident)
	return randuri, ascunse


def muta_albastru(randuri, ascunse, automate, ident, pas):
	"""Muta un rand bifat cu `pas` locuri (-1 sus, 1 jos). Din acel moment ordinea tuturor randurilor bifate e a omului."""
	lista = in_lista_albastra(randuri, ascunse, automate)
	if ident not in lista:
		return list(randuri), list(ascunse)
	i = lista.index(ident)
	j = max(0, min(len(lista) - 1, i + pas))
	lista.insert(j, lista.pop(i))
	return lista, list(ascunse)


def _plugin_din_rand(ext):
	"""Pluginul unui rand din InfoBarPlugins.getPluginList (boundFunction(self.runPlugin, p)), sau None."""
	args = getattr(ext[1], "args", None)
	if args and hasattr(args[0], "fnc") and hasattr(args[0], "path"):
		return args[0]
	return None


def id_rand_imagine(ext):
	"""Identificatorul unui rand pus de imagine (addExtension), dupa functia lui; None pentru cele necunoscute."""
	nume = getattr(ext[1], "__name__", "")
	if nume in _RANDURI_IMAGINE:
		return _RANDURI_IMAGINE[nume]
	if nume == "<lambda>":
		try:
			if ext[0]() == _tr(N_("Subcanale")):
				return "imagine:subcanale"
		except Exception:
			return None
	return None


def _scurtatura(ident):
	for s in SCURTATURI_ALBASTRU:
		if s[0] == ident:
			return s
	return None


def _index_meniu():
	from Components import HdsCautaSetari
	return HdsCautaSetari.index()


def _mesaj(sesiune, text):
	from Screens.MessageBox import MessageBox
	sesiune.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=8)


def _porneste_sigur(ecran, functie):
	"""Un rand ales care nu merge pe ecranul acesta (de pilda in playerul de filme) spune asta, nu opreste interfata."""
	def porneste():
		try:
			functie()
		except Exception as e:
			print("[HdsTasteRapide] lista albastra: %s: %s" % (type(e).__name__, e))
			_mesaj(ecran.session, _tr(N_("Nu se poate deschide de aici.")))
	return porneste


def deschide_meniu_albastru(ecran, cheie):
	from Components import HdsCautaSetari
	intrare = _index_meniu().dupaCheie(cheie)
	if intrare is None:
		_mesaj(ecran.session, _tr(N_("Nu se poate deschide de aici.")))
		return
	ecran.session.infobar = ecran
	HdsCautaSetari.deschide(ecran.session, intrare)


def _mesaj_amanat(text, ident):
	"""Un mesaj cerut de un ceas sau de sfarsitul unei lucrari: in coada notificarilor enigma2 (Tools/Notifications.AddPopup),
	care il arata cand bara e iar ecranul de sus. Un Session.open direct de aici ar putea cadea cu "modal open are allowed
	only from a screen which is modal" daca tocmai se inchide alt ecran."""
	from Tools import Notifications
	from Screens.MessageBox import MessageBox
	Notifications.AddPopup(text, MessageBox.TYPE_INFO, 8, ident)


def reporneste_reteaua(sesiune):
	"""Ca "Restart network" din ecranul placii de retea (Components/HdsRetea.reporneste), cu un mesaj la inceput (din
	randul ales, ecranul de sus e bara) si unul la sfarsit, prin coada notificarilor."""
	from Components import HdsRetea
	_mesaj(sesiune, _tr(N_("Repornesc rețeaua. Durează câteva secunde.")))
	HdsRetea.reporneste(lambda *a: _mesaj_amanat(_tr(N_("Rețeaua a repornit.")), "hds_albastru_retea"))


_CEASURI_VITEZA = []


def testul_de_viteza(sesiune, V=None, ceas=None):
	"""Testul de viteza din ecranul VPN (Components/HdsVpn.testViteza: prin VPN cand e pornit, altfel direct), pe firul
	lucrarilor lui; aici se asteapta rezultatul cu un ceas pe firul enigma2. Fereastra de asteptare se inchide numai cand
	e chiar ecranul de sus (altfel o inchide omul), iar rezultatul merge in coada notificarilor (_mesaj_amanat): din ceas
	nu se deschide niciun ecran direct."""
	from Screens.MessageBox import MessageBox
	if V is None:
		from Components import HdsVpn as V
	numar = V.pornesteViteza()
	if numar is None:
		_mesaj(sesiune, _tr(N_("Așteaptă să se termine ce ai pornit înainte.")))
		return
	asteapta = sesiune.open(MessageBox, _tr(N_("Măsor viteza internetului, cel mult 10 secunde...")), MessageBox.TYPE_INFO)
	if ceas is None:
		from enigma import eTimer
		ceas = eTimer()
	pasi = [0]

	def verifica():
		ultima = V.LUCRARI.stare().get("ultima") or {}
		pasi[0] += 1
		if ultima.get("id") != numar and pasi[0] < 60:
			ceas.start(500, True)
			return
		if ceas in _CEASURI_VITEZA:
			_CEASURI_VITEZA.remove(ceas)
		if ultima.get("id") == numar:
			text = ultima.get("mesaj") or ""
		else:
			text = _tr(N_("Testul de viteză nu a mers. Verifică legătura la internet."))
		if getattr(sesiune, "current_dialog", None) is asteapta and getattr(sesiune, "in_exec", False):
			try:
				asteapta.close()
			except Exception as e:
				print("[HdsTasteRapide] testul de viteza: fereastra de asteptare: %s" % e)
		_mesaj_amanat(text, "hds_albastru_viteza")
	ceas.callback.append(verifica)
	_CEASURI_VITEZA.append(ceas)
	ceas.start(500, True)


def _cu_lista_canale(ecran):
	try:
		from Screens.InfoBarGenerics import InfoBarChannelSelection
		return isinstance(ecran, InfoBarChannelSelection)
	except ImportError:
		return hasattr(ecran, "servicelist")


def rand_ales(ecran, ident, pluginuri=None):
	"""(numele, porneste, disponibil) pentru un rand ales de om, ca randurile puse cu addExtension; None cand nu se
	poate deschide acum."""
	s = _scurtatura(ident)
	if s is not None:
		_id, text, cheie, cere = s
		if cere:
			from Components.SystemInfo import SystemInfo
			if not SystemInfo.get(cere):
				return None
		if cheie:
			if _index_meniu().dupaCheie(cheie) is None:
				return None
			fn = lambda: deschide_meniu_albastru(ecran, cheie)
		elif ident == "gata:retea":
			fn = lambda: reporneste_reteaua(ecran.session)
		else:
			fn = lambda: testul_de_viteza(ecran.session)
		return (lambda: _tr(text), _porneste_sigur(ecran, fn), lambda: True)
	fel, _sep, rest = ident.partition(":")
	if fel == "m":
		intrare = _index_meniu().dupaCheie(ident)
		if intrare is None:
			return None
		nume = intrare.nume
		return (lambda: nume, _porneste_sigur(ecran, lambda: deschide_meniu_albastru(ecran, ident)), lambda: True)
	if fel == "plugin":
		p = (pluginuri if pluginuri is not None else pluginuri_alocabile()).get(ident)
		if p is None or (p.cereListaCanale() and not _cu_lista_canale(ecran)):
			return None
		nume = str(p.name)
		return (lambda: nume, _porneste_sigur(ecran, lambda: ecran.runPlugin(p)), lambda: True)
	if fel == "tasta" and rest in dict(ACTIUNI_DISPONIBILE) and rest not in _ACTIUNI_FARA_LISTA:
		text = dict(ACTIUNI_DISPONIBILE)[rest]

		def fa():
			from Screens.InfoBar import hdsFaActiuneaLunga
			hdsFaActiuneaLunga(ecran, rest)
		return (lambda: _tr(text), _porneste_sigur(ecran, fa), lambda: True)
	return None


def _disponibil(ext):
	try:
		return bool(ext[2]())
	except Exception:
		return False


def sursa_listei(ecran, lista, config=None):
	"""Lista din care InfoBarExtensions.updateExtensions face randurile si tastele lor. Fara alegerea omului: `lista`
	insasi, neatinsa. Cu alegere: intai randurile alese, in ordinea lor (fara tasta proprie, deci cu cifrele 1, 2, ... in
	ordine), apoi restul listei de pana acum fara cele ascunse si fara cele deja mutate sus. Elementele: (fel, rand,
	tasta), ca in addExtension; 0 = un rand, altfel o functie care da randurile (pluginurile, lucrarile)."""
	randuri, ascunse = alegere_albastru(config)
	if not randuri and not ascunse:
		return lista
	cheiPluginuri = None
	gasite = []        # (identificatorul sau None, elementul)
	for x in lista:
		if x[0] == 0:
			gasite.append((id_rand_imagine(x[1]), x))
		elif getattr(x[1], "__name__", "") == "getPluginList":
			if cheiPluginuri is None:
				toate = pluginuri_alocabile()
				cheiPluginuri = (toate, dict((id(p), k) for k, p in toate.items()))
			for y in x[1]():
				p = _plugin_din_rand(y[0])
				gasite.append((cheiPluginuri[1].get(id(p)) if p is not None else None, (0, y[0], y[1])))
		else:
			gasite.append((None, x))
	alese = set(randuri)
	rez = []
	for ident in randuri:
		if ident in ascunse:
			continue
		ale = [x for i, x in gasite if i == ident]
		if ale:
			# mutate in ordinea omului, fara tasta lor (ALBASTRU la PiP): numai cele care se pot deschide acum, ca un
			# rand ascuns sa nu tina o cifra
			rez.extend((0, x[1], None) for x in ale if _disponibil(x[1]))
			continue
		try:
			r = rand_ales(ecran, ident, cheiPluginuri[0] if cheiPluginuri else None)
		except Exception as e:
			print("[HdsTasteRapide] lista albastra: randul %s: %s" % (ident, e))
			r = None
		if r is not None:
			rez.append((0, r, None))
	for ident, x in gasite:
		if ident is not None and (ident in ascunse or ident in alese):
			continue
		rez.append(x)
	return rez


def catalog_albastru(config=None, pluginuri=None, SystemInfo=None, index=None, tr=None):
	"""Tot ce se poate pune in lista ALBASTRA, pentru ecranul de alegere si pagina web: [{id, nume, grupa, automat}], in
	ordinea: randurile care se pun singure (ca in lista de acum), scurtaturile gata, functiile tastelor, meniurile,
	pluginurile. tr: functia de traducere a paginii web (altfel cea a enigma2)."""
	t = (lambda x: text_tasta("", x, tr)) if tr is not None else _tr
	if SystemInfo is None:
		try:
			from Components.SystemInfo import SystemInfo
		except ImportError:
			SystemInfo = {}
	if pluginuri is None:
		from Components.PluginComponent import plugins
		pluginuri = plugins
	from Components.HdsExtensiiLucru import pluginuriAlbastru
	toate = pluginuri_alocabile(pluginuri.pluginuriDeDeschis())
	chei = dict((id(p), k) for k, p in toate.items())
	rez = [{"id": "imagine:acces", "nume": t(N_("Acces condiționat")), "grupa": t(N_("Se pune singur")), "automat": True}]
	vazute = set(["imagine:acces"])
	for p in sorted(pluginuriAlbastru(pluginuri), key=lambda p: str(p.name).lower()):
		k = chei.get(id(p))
		if k and k not in vazute:
			vazute.add(k)
			rez.append({"id": k, "nume": str(p.name), "grupa": t(N_("Plugin, se pune singur")), "automat": True})
	rez.append({"id": "imagine:subcanale", "nume": t(N_("Subcanale")), "grupa": t(N_("Se pune singur")), "automat": True})
	if SystemInfo.get("NumVideoDecoders", 1) > 1:
		rez.append({"id": "imagine:pip", "nume": t(N_("Pornește sau oprește PiP")), "grupa": t(N_("Se pune singur")), "automat": True})
	for ident, text, _cheie, cere in SCURTATURI_ALBASTRU:
		if not cere or SystemInfo.get(cere):
			rez.append({"id": ident, "nume": t(text), "grupa": t(N_("Scurtătură")), "automat": False})
	for k, text in ACTIUNI_DISPONIBILE:
		if k not in _ACTIUNI_FARA_LISTA:
			rez.append({"id": "tasta:" + k, "nume": t(text), "grupa": t(N_("Funcție")), "automat": False})
	try:
		idx = index if index is not None else _index_meniu()
		dubluri = set()
		for i in idx.intrari:
			if i.fel not in ("grup", "intrare") or i.cheie in vazute:
				continue
			d = i.dublura()
			if d in dubluri:
				continue
			dubluri.add(d)
			vazute.add(i.cheie)
			rez.append({"id": i.cheie, "nume": i.nume, "grupa": i.drumText(t), "automat": False})
	except Exception as e:
		print("[HdsTasteRapide] lista albastra: meniurile: %s" % e)
	for k, p in sorted(toate.items(), key=lambda x: (str(x[1].name).lower(), x[0])):
		if k not in vazute:
			vazute.add(k)
			rez.append({"id": k, "nume": str(p.name), "grupa": t(N_("Plugin")), "automat": False})
	return rez


def stare_albastru(config=None, catalog=None, **optiuni):
	"""{randuri, ascunse, automate, lista (bifate, in ordine), catalog}: ce arata ecranul de alegere si pagina web."""
	catalog = catalog if catalog is not None else catalog_albastru(config, **optiuni)
	randuri, ascunse = alegere_albastru(config)
	automate = [x["id"] for x in catalog if x["automat"]]
	return {"randuri": randuri, "ascunse": ascunse, "automate": automate,
		"lista": in_lista_albastra(randuri, ascunse, automate), "catalog": catalog}


def schimba_albastru(actiune, ident="", config=None, configfile=None, catalog=None, **optiuni):
	"""O schimbare a omului, salvata pe loc: actiune = comuta | sus | jos | fabrica. Intoarce starea noua, sau None
	pentru o cerere necunoscuta (un rand care nu e in catalog si nici in alegere)."""
	st = stare_albastru(config, catalog, **optiuni)
	randuri, ascunse, automate = st["randuri"], st["ascunse"], st["automate"]
	cunoscute = set(x["id"] for x in st["catalog"]) | set(randuri) | set(ascunse)
	if actiune == "fabrica":
		randuri, ascunse = [], []
	elif ident not in cunoscute:
		return None
	elif actiune == "comuta":
		randuri, ascunse = comuta_albastru(randuri, ascunse, automate, ident)
	elif actiune in ("sus", "jos"):
		randuri, ascunse = muta_albastru(randuri, ascunse, automate, ident, -1 if actiune == "sus" else 1)
	else:
		return None
	salveaza_albastru(randuri, ascunse, config, configfile)
	return stare_albastru(config, st["catalog"])
