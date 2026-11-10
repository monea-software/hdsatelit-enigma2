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

ACTIUNI_DISPONIBILE = [
	("default", _("Funcția obișnuită")),
	("none", _("Nimic")),
	("epg", _("Alegerea tipului de ghid (EPG)")),
	("epg_multi", _("Ghidul buchetului curent")),
	("epg_single", _("Ghidul canalului curent")),
	("eventinfo", _("Detaliile emisiunii")),
	("subtitle_toggle", _("Pornește sau oprește ultima subtitrare")),
	("portal", _("Portal")),
	("menu", _("Meniu principal")),
	("plugins", _("Plugins & Applications")),
	("extensions", _("Lista extensiilor (ca ALBASTRU)")),
	("info", _("Informații sistem")),
	("audio", _("Selectare pistă audio")),
	("subtitle", _("Subtitrări")),
	("channellist", _("Lista de canale")),
	("favourites", _("Favorite")),
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

VALORI_IMPLICITE = dict((k, "default") for k, _text in SCURTE + BUTOANE)
VALORI_IMPLICITE.update(red="none", green="none", yellow="none",
	blue="none", green_short="subservices", yellow_short="audio", blue_short="extensions")

# Sensul functiei obisnuite se pastreaza intr-un singur loc.
FUNCTII_OBISNUITE = {
	"info_short": "eventinfo", "info_long": "epg",
	"epg_short": "epg_multi", "epg_long": "epg",
	"subtitle_short": "subtitle_toggle", "subtitle_long": "subtitle",
	"green_short": "subservices", "yellow_short": "audio", "blue_short": "extensions",
	"red": "none", "green": "none", "yellow": "none", "blue": "none",
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
	("hds_fav_scurt_adauga", False, _("FAV scurt adaugă sau scoate canalul din Favorite")),
	("hds_ok_lung_cauta", False, _("OK lung caută în lista de canale")),
	("hds_text_lista_cauta", False, _("TEXT caută în lista de canale")),
	("hds_meniu_galben_aspect", False, _("GALBEN schimbă lista sau dalele în meniu")),
	("hds_meniu_text_cauta", False, _("TEXT caută setări în meniu")),
	("hds_filme_culori_vechi", False, _("Culorile vechi în lista de filme")),
	("hds_ch_privire", "device", _("CH+ și CH- la privit")),
	("hds_exit_film", "hide", _("EXIT în timpul filmului")),
)
ALEGERI_CH = (("device", _("După telecomandă")),
	("zap", _("Schimbă canalul")), ("list", _("Deschide lista de canale")))
ALEGERI_PROFIL = {"hds_ch_privire": ALEGERI_CH,
	"hds_exit_film": (("hide", _("Ascunde bara de informații")), ("ask", _("Ask user")),
		("movielist", _("Return to movie list")), ("quit", _("Return to previous service")))}


def initConfigProfil(config=None):
	config = _config(config)
	from Components.config import ConfigYesNo, ConfigSelection, ConfigSubsection
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	u = config.usage
	for k, implicit, _text in PROFIL_SETARI:
		if k not in u.content.items:
			setattr(u, k, ConfigYesNo(default=implicit) if isinstance(implicit, bool)
				else ConfigSelection(default=implicit, choices=list(ALEGERI_PROFIL[k])))
	return u


def optiune(nume, config=None):
	"""Valoarea curenta sau fabrica, inclusiv inainte de initializarea interfetei."""
	try:
		return getattr(_config(config).usage, nume).value
	except (AttributeError, KeyError, ImportError):
		return dict((k, v) for k, v, _text in PROFIL_SETARI).get(nume)


def actiune_efectiva(buton, config=None):
	valoare = actiune_aleasa(buton, config)
	return FUNCTII_OBISNUITE.get(buton, "default") if valoare == "default" else valoare


TEXTE_ACTIUNI = {
	"none": _("Nimic"), "default": _("Funcția obișnuită"),
	"hbbtv": _("HbbTV"), "record": _("Înregistrează"),
	"eventinfo": _("Detaliile emisiunii"), "epg_multi": _("Ghidul buchetului curent"),
	"epg_single": _("Ghidul canalului curent"), "epg": _("Alegerea tipului de ghid (EPG)"),
	"subtitle_toggle": _("Pornește sau oprește ultima subtitrare"), "subtitle": _("Lista subtitrărilor"),
	"subservices": _("Subcanale"), "audio": _("Selectare pistă audio"),
	"extensions": _("Lista extensiilor"), "portal": _("Portal"),
	"bouquets": _("Lista buchetelor și favoritelor"), "favourites": _("Favorite"),
	"favorite_toggle": _("Adaugă sau scoate canalul din Favorite"),
	"favorite_choose_bouquet": _("Alege buchetul pentru canal"),
	"select_channel": _("Alege canalul de sub cursor"), "search_channels": _("Caută canale"),
	"toggle_layout": _("Listă sau dale"), "search_settings": _("Caută setări"),
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
}


def text_actiune(actiune):
	if actiune.startswith("plugin:"):
		p = pluginuri_alocabile().get(actiune)
		return _("Plugin: %s") % p.name if p else _("Plugin indisponibil (%s)") % actiune[-8:]
	return TEXTE_ACTIUNI.get(actiune, dict(ACTIUNI_DISPONIBILE).get(actiune, actiune))


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
			"exit": "pip_close" if stare.get("pip") else "hide", "play": "play",
			"pause": "pause" if context == "timeshift" else "timeshift",
			"stop": "stop_timeshift", "portal": "portal", "menu": "menu"}.get(key, "default")
	if context == "channel_list":
		if key == "fav":
			return "favorite_choose_bouquet" if lung else (
				"favorite_toggle" if optiune("hds_fav_scurt_adauga", config) else "bouquets")
		if key == "ok":
			return ("search_channels" if optiune("hds_ok_lung_cauta", config) else "none") if lung else "select_channel"
		if lung:
			return "none"
		return {"text": "search_channels" if optiune("hds_text_lista_cauta", config) else "none",
			"channelup": "next_bouquet", "channeldown": "previous_bouquet"}.get(key, "default")
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
	if context == "button_setup":
		context = "setup"
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


def initConfigButtonSetup(config=None):
	# Verificam dictionarul: unele versiuni de ConfigSubsection arunca KeyError.
	config = _config(config)
	chei = [k for k, _text in SCURTE + BUTOANE]
	if "hds_buttons" in config.content.items:
		b = config.hds_buttons
		cunoscute = getattr(getattr(b, "content", None), "items", vars(b))
		if all(k in cunoscute for k in chei):
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
	alegeri = ACTIUNI_DISPONIBILE + [
		(k, _("Plugin: %s") % p.name) for k, p in sorted(
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

	def __init__(self, porneste, numar, disponibila, config=None, ceas=None):
		self.porneste = porneste
		self.numar = numar
		self.disponibila = disponibila
		self.config = config
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
		a = actiune_efectiva(scurta, self.config) if scurta else "default"
		l = actiune_efectiva(lunga, self.config) if lunga else "default"
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
