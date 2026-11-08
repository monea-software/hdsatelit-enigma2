# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pregatirea Radio online, comuna televizorului si paginii web.

Catalogul se citeste pe un fir separat. Descarcarea listei si instalarea trec
numai prin HdsExtensiiLucru; starea ramane vie si dupa inchiderea ecranului.
Metodele Pregatire se cheama pe firul interfetei.
"""
import builtins
import os
import threading


PACHET = "enigma2-plugin-extensions-radioonline"
PLUGIN = "/usr/lib/enigma2/python/Plugins/Extensions/RadioOnline"
FAZE_ACTIVE = ("citesc", "lista", "instalare")


def _(text):
	traducere = getattr(builtins, "_", None)
	return traducere(text) if traducere is not None else text


def text_confirmare():
	return _("Radio online nu e instalat. Îl instalez acum?")


def plugin_instalat(cale=PLUGIN):
	return any(os.path.isfile(os.path.join(cale, nume)) for nume in ("plugin.py", "plugin.pyc"))


def _X():
	from Components import HdsExtensiiLucru
	return HdsExtensiiLucru


def _pe_fir(lucru, gata):
	"""lucru() pe un fir separat, gata(rezultat, eroare) pe firul interfetei."""
	from twisted.internet import reactor

	def alearga():
		rezultat, eroare = None, None
		try:
			rezultat = lucru()
		except Exception as e:
			eroare = e
		reactor.callFromThread(gata, rezultat, eroare)

	threading.Thread(target=alearga, name="HdsRadioOnline", daemon=True).start()


def _ceas():
	from enigma import eTimer
	return eTimer()


def _motiv_scurt(date, implicit):
	"""Doar motive pentru om; iesirea integrala ramane in jurnalul Extensiilor."""
	text = "\n".join(str(x) for x in (date or ())).lower()
	if "no space left" in text or "only have" in text and "available" in text or "nu mai este loc" in text:
		return _("Nu mai este loc în memoria receptorului.")
	if "lock" in text or "altă instalare" in text:
		return _("Altă instalare rulează acum. Încearcă din nou mai târziu.")
	if any(x in text for x in ("unknown package", "cannot find package", "no candidates", "nu se mai află în feed")):
		return _("Radio online nu este disponibil în feedul acestui receptor.")
	if any(x in text for x in ("architectur", "not compatible", "nu este făcută", "python")):
		return _("Radio online nu este disponibil pentru acest receptor.")
	if "signature" in text or "semnătura" in text:
		return _("Lista de programe nu a putut fi verificată. Încearcă din nou mai târziu.")
	if "ceasul" in text or "certificate" in text:
		return _("Verifică data și ora receptorului, apoi încearcă din nou.")
	if any(x in text for x in ("mismatch", "malformed", "error unpacking", "deteriorat", "nu se poate citi")):
		return _("Fișierul descărcat nu se poate folosi. Încearcă din nou.")
	if any(x in text for x in ("download", "wget", "curl", "network", "resolve", "timed out", "connection", "internet")):
		return _("Nu s-a putut descărca Radio online. Verifică legătura la internet.")
	return implicit


class Pregatire(object):
	"""O singura instalare pentru TV si web, fara asteptarea retelei pe firul lor.

	Faze: nimic, citesc, lista, de_instalat, instalare, gata, lipsa, eroare.
	Progresul este None cand instalatorul nu ofera un procent masurat.
	"""

	def __init__(self, X=None, pe_fir=_pe_fir, instalat=plugin_instalat, ceas=None, plugins=None):
		self._x = X
		self.pe_fir = pe_fir
		self.instalat = instalat
		self._ceas_nou = ceas or _ceas
		self._plugins = plugins
		self._ceas = None
		self.faza = "nimic"
		self.text = ""
		self.marime = 0
		self.catalog = None
		self.pachet = None
		self.lucrare = None
		self.a_cerut_lista = False
		self.vrea_instalare = False
		self._instalare_esuat = False

	def X(self):
		return self._x if self._x is not None else _X()

	def _pune(self, faza, text=""):
		self.faza, self.text = faza, text
		if faza in ("gata", "lipsa", "eroare"):
			self.vrea_instalare = False
		if faza not in FAZE_ACTIVE and self._ceas is not None:
			self._ceas.stop()

	def _eroare(self, text):
		self.vrea_instalare = False
		self._pune("eroare", text)

	def _urmareste(self):
		if self.faza not in FAZE_ACTIVE:
			return
		if self._ceas is None:
			self._ceas = self._ceas_nou()
			self._ceas.callback.append(self._sondeaza)
		self._ceas.start(250)

	def verifica(self, instaleaza=False):
		"""Fara argument: doar verificare. True: verificare si instalare dupa Da."""
		if instaleaza:
			self.vrea_instalare = True
		if self.faza == "instalare":
			return
		if self.instalat() and not self._instalare_esuat:
			self.vrea_instalare = False
			self._pune("gata")
			return
		if self.faza in FAZE_ACTIVE:
			return
		self.a_cerut_lista = False
		self.catalog, self.pachet, self.marime = None, None, 0
		self._citeste_catalog()

	def _citeste_catalog(self):
		self._pune("citesc", _("Verific dacă Radio online este disponibil..."))
		try:
			self.pe_fir(self.X().incarcaCatalog, self._catalog_citit)
		except Exception as e:
			print("[HdsRadioOnline] citirea listei: %s" % type(e).__name__)
			self._eroare(_("Nu am putut citi lista de programe. Încearcă din nou."))

	def _catalog_citit(self, catalog, eroare):
		if self.instalat() and not self._instalare_esuat:
			self.vrea_instalare = False
			self._pune("gata")
			return
		if eroare is not None or catalog is None:
			self._eroare(_("Nu am putut citi lista de programe. Încearcă din nou."))
			return
		try:
			self.catalog = catalog
			self.pachet = catalog._toate.get(PACHET)
			if self.pachet is None or not getattr(self.pachet, "disponibil", True):
				self.pachet = None
				if not self.a_cerut_lista:
					self.a_cerut_lista = True
					self._cere_lista()
					return
				self.vrea_instalare = False
				self._pune("lipsa", _("Radio online nu este disponibil în feedul acestui receptor."))
				return
			dependente = catalog.dependente_de_instalat(self.pachet)
			self.marime = self.pachet.marime + sum(p.marime for p in dependente)
			self._pune("de_instalat", _("Radio online este disponibil pentru instalare."))
			if self.vrea_instalare:
				self.instaleaza()
		except Exception as e:
			print("[HdsRadioOnline] verificarea listei: %s" % type(e).__name__)
			self._eroare(_("Nu am putut verifica Radio online. Încearcă din nou."))

	def _cere_lista(self):
		X = self.X()
		self._pune("lista", _("Se descarcă lista de programe..."))
		try:
			if not X.descarcareInCurs():
				ocupat = X.motivOcupat()
				if ocupat is not None:
					self._eroare(ocupat[0])
					return
				X.pornesteDescarcarea()
			self._urmareste()
			self._sondeaza()
		except Exception as e:
			print("[HdsRadioOnline] descarcarea listei: %s" % type(e).__name__)
			self._eroare(_("Lista de programe nu s-a putut descărca. Verifică legătura la internet."))

	def instaleaza(self):
		"""Porneste numai dupa acord; apelurile repetate urmaresc aceeasi lucrare."""
		if self.faza == "instalare":
			return
		if self.instalat() and not self._instalare_esuat:
			self.vrea_instalare = False
			self._pune("gata")
			return
		if self.faza in ("citesc", "lista"):
			self.vrea_instalare = True
			return
		if self.pachet is None or self.catalog is None or self.faza != "de_instalat":
			self.verifica(True)
			return
		self.vrea_instalare = False
		try:
			X = self.X()
			ocupat = X.motivOcupat()
			if ocupat is not None:
				self._eroare(ocupat[0])
				return
			plan, eroare = X.planInstalare(self.catalog, self.pachet)
			if plan is None or plan.get("fel") != "instaleaza":
				self._eroare(_motiv_scurt([eroare[0]] if eroare else [],
					_("Radio online nu se poate instala acum. Încearcă din nou mai târziu.")))
				return
			plugins = self._plugins
			if plugins is None:
				from Components.PluginComponent import plugins
			self._pune("instalare", _("Se instalează Radio online..."))
			self.lucrare = X.pornesteLucrarea(plan, plugins=plugins, din_web=False)
			self.lucrare.asculta(self._lucrare)
			# Pornirea poate esua sincron, inainte de inregistrarea ascultatorului.
			self._urmareste()
			self._sondeaza()
		except Exception as e:
			print("[HdsRadioOnline] pornirea instalarii: %s" % type(e).__name__)
			if self.faza == "instalare":
				self._instalare_esuat = True
			self._eroare(_("Radio online nu s-a instalat. Încearcă din nou."))

	def _lucrare(self, fel, *date):
		if fel != "gata" or self.lucrare is None:
			return
		lucrare, self.lucrare = self.lucrare, None
		lasa = getattr(lucrare, "lasa", None)
		if lasa is not None:
			lasa(self._lucrare)
		cod = date[0] if date else getattr(lucrare, "cod", None)
		rezultat = getattr(lucrare, "rezultat", None) or {}
		if rezultat.get("reusit", cod == 0) and self.instalat():
			self._instalare_esuat = False
			self._pune("gata")
			return
		self._instalare_esuat = True
		linii = list(getattr(lucrare, "linii", None) or [])
		linii.append(rezultat.get("stare", ""))
		self._eroare(_motiv_scurt(linii, _("Radio online nu s-a instalat. Încearcă din nou.")))

	def _sondeaza(self):
		if self.faza == "lista" and not self.X().descarcareInCurs():
			rezultat = (getattr(self.X(), "STARE", None) or {}).get("descarcare") or {}
			if rezultat.get("cod", 0) != 0:
				self._eroare(_motiv_scurt([rezultat.get("motiv", "")],
					_("Lista de programe nu s-a putut descărca. Verifică legătura la internet.")))
				return
			self._citeste_catalog()
		elif self.faza == "instalare" and self.lucrare is not None and getattr(self.lucrare, "faza", None) == "gata":
			self._lucrare("gata", getattr(self.lucrare, "cod", None))

	def stare(self):
		"""{faza, text, marime (octeti), pas, progres (None sau 100)}; fara pornire implicita."""
		self._sondeaza()
		instalat = self.instalat()
		if self.faza == "gata" and not instalat:
			self.catalog, self.pachet, self.marime = None, None, 0
			self._pune("nimic")
		elif self.faza not in FAZE_ACTIVE and instalat and not self._instalare_esuat:
			self._pune("gata")
		pas = ""
		if self.faza == "instalare" and self.lucrare is not None:
			pas = _("Se descarcă Radio online...") if getattr(self.lucrare, "etapa", None) == "verificare" else _("Se pregătește programul de radio...")
		return {"faza": self.faza, "text": self.text, "marime": self.marime, "pas": pas,
			"progres": 100 if self.faza == "gata" else None}


_pregatire = []


def pregatire():
	if not _pregatire:
		_pregatire.append(Pregatire())
	return _pregatire[0]
