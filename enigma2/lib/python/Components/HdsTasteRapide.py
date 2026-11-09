# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Setarile comune ale ecranului si paginii /taste-rapide.
# Functia obisnuita lasa tasta pe hartile barei, dupa telecomanda si canal.
# Numele setarilor vechi raman valabile. Nicio dependenta nativa la import.

ACTIUNI_DISPONIBILE = [
	("default", _("Funcția obișnuită")),
	("none", _("Nimic")),
	("epg", _("Ghid programe (EPG)")),
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
VALORI_IMPLICITE.update(red="channellist", green="audio", yellow="subtitle",
	blue="epg", green_short="plugins", blue_short="extensions")

# Tasta fizica, setarea scurta, setarea lunga, scurta la eliberare.
# Numerele pastreaza selectia canalului la apasare pana li se aloca ceva lung.
LEGATURI_TASTE = [
	("red", "red_short", "red", True),
	("green", "green_short", "green", True),
	("yellow", "yellow_short", "yellow", True),
	("blue", "blue_short", "blue", True),
	("info", "info_short", "info_long", True),
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


def initConfigButtonSetup(config=None):
	# Verificam dictionarul: unele versiuni de ConfigSubsection arunca KeyError.
	config = _config(config)
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
	return getattr(initConfigButtonSetup(config), buton).value


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
		a = actiune_aleasa(scurta, self.config) if scurta else "default"
		l = actiune_aleasa(lunga, self.config) if lunga else "default"
		if l == "default" and tasta in ("red", "green", "yellow", "blue"):
			l = VALORI_IMPLICITE[tasta]
		# VERDE isi pastreaza traseul vechi pentru cele doua valori istorice.
		proprie = a != "default"
		if tasta == "green" and a in ("plugins", "none"):
			proprie = False
		if tasta == "blue" and a == "extensions":
			proprie = False
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
				if l == "none" and tasta in ("red", "green", "yellow", "blue"):
					return int(proprie)
				self._opreste_asteptarea()
				self.incheiate.add(tasta)
				self.lungi.add(tasta)
				print("[HdsTasteRapide] tasta=%s semn=l decizie=lunga" % tasta)
				self.porneste(tasta, l)
				return 1
			if proprie and la_eliberare and tasta in ("info", "audio", "fav"):
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
