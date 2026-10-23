# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWebControlSetup.py: ecranul de configurare pentru serverul HdsWebControl
# (Plugins/Extensions/HdsWebControl/plugin.py, care porneste efectiv serverul
# Twisted la pornirea sesiunii). Cod 100% propriu, scris de la zero.
#
# Preferintele (activ/dezactivat, port) se aplica la urmatoarea pornire a interfetei (Restart Interface
# din meniu), la fel ca la majoritatea preferintelor de retea din Enigma2.
#
# ecranul arata adresa de deschis in browser, browserele conectate cu
# codul de pe televizor si le poate deconecta pe toate (Galben, cu confirmare). Efectul e imediat, fara
# repornire: ecranul si serverul folosesc acelasi obiect de asociere (obtineAsociere(), acelasi proces).
# Cheia pentru scripturi (fostul "jeton") ramane, afisata mic, cu "Cheie nouă pentru panoul web" sub Albastru > Alte
# optiuni (inainte pe Galben): cu confirmare, cheie noua si toate aparatele asociate deconectate (cine avea cheia
# veche putea asocia un aparat), apoi mesajul cu ce urmeaza (internet_web.cheieNouaPanou, aceeasi ca in web).
#
# orice aparat din retea putea tine asocierea blocata (5 coduri gresite la fiecare
# 5 minute) sau putea consuma cele 10 afisari de cod; doar repornirea enigma2 scotea blocarea. Albastru > Alte
# optiuni > "Conectează un browser nou" o scoate din telecomanda si arata codul chiar aici, fara sa astepte
# iesirea din meniu (notificarile obisnuite apar doar peste InfoBar).
#
# Codul se arata in fereastra Screens/HdsCodAsociere.py (codul mare, „12 34 56”), aceeasi ca
# pentru codul cerut din browser; OK sau EXIT il anuleaza, iar dupa o ora fara conectare apare mesajul scurt de
# expirare. Randul „Cere codul și în rețeaua locală” (implicit Nu: aparatele din casa intra fara
# cod; din afara retelei locale receptorul nu raspunde oricum) se aplica imediat la Salvează, fara repornire. Acelasi
# rand e si in web, pe pagina /setari (caseta „Interfața web”).
#
# randul „Aplicații de telefon” (pornit din fabrica) tine pornite
# rutele pentru aplicatiile obisnuite ale receptoarelor Enigma2 (canale, telecomanda, ghid, inregistrari, liste m3u);
# din casa merg fara parola (cu „Cere codul și în rețeaua locală” pornit, si din casa numai cu
# utilizatorul root si parola pentru aplicatii). Randul de sub el, „Acces din afara casei” (oprit din fabrica), le lasa sa
# raspunda si din afara retelei locale, numai cu utilizatorul root si parola pentru aplicatii. Eticheta de sub cheia
# pentru scripturi spune ce scrii in aplicatie din casa si din afara, parola (facuta acum, prima data) si aplicatiile
# conectate; Albastru > Alte optiuni > „Parolă nouă pentru aplicații” o schimba. Se aplica imediat, ca randul codului;
# aceleasi randuri sunt si in web, in caseta „Interfața web” din /setari.

import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry
from Components.Sources.StaticText import StaticText

from Plugins.Extensions.HdsWebControl.plugin import initConfigHdsWebControl, obtineAsociere, adresaWeb
from Plugins.Extensions.HdsWebControl import aplicatii_web

# cate browsere incap pe ecran; restul se numara ("si inca N")
_BROWSERE_PE_ECRAN = 5
# cate aplicatii de telefon conectate se scriu pe randul parolei
_APLICATII_PE_ECRAN = 3


class HdsWebControlSetup(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsWebControlSetup" resolution="1920,1080" position="center,center" size="1000,700" title="Interfața web HD Satelit (HdsWebControl)">
		<widget name="config" position="30,15" size="940,212" scrollbarMode="showOnDemand" font="Regular;24" secondfont="Regular;24" itemHeight="42" />
		<widget source="ghid" render="Label" position="30,230" size="940,76" font="Regular;21" />
		<widget source="browsere" render="Label" position="30,308" size="940,160" font="Regular;20" />
		<widget source="jeton" render="Label" position="30,470" size="940,26" font="Regular;17" foregroundColor="#a08000" noWrap="1" transparent="1" />
		<widget source="aplicatii" render="Label" position="30,498" size="940,130" font="Regular;17" foregroundColor="#7fb8ff" />
		<widget source="key_red" render="Label" position="30,640" size="220,45" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="265,640" size="220,45" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="500,640" size="220,45" zPosition="1" font="Regular;19" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget source="key_blue" render="Label" position="735,640" size="235,45" zPosition="1" font="Regular;21" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		# on_change: la stanga/dreapta pe un rand, ghidul se reface (fara notificator pe setare: acela ramanea legat
		# de ecranul inchis si cadea la urmatoarea schimbare, vazut in emulator)
		ConfigListScreen.__init__(self, [], session=session, on_change=self._actualizeazaGhid)
		self.setTitle(_("Interfața web HD Satelit (HdsWebControl)"))
		initConfigHdsWebControl()

		self._adresa = adresaWeb()
		self["ghid"] = StaticText("")
		self["browsere"] = StaticText("")
		self["jeton"] = StaticText("")
		self["aplicatii"] = StaticText("")
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Deconectează browserele"))
		self["key_blue"] = StaticText(_("Alte opțiuni"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.anuleaza,
				"red": self.anuleaza,
				"green": self.salveaza,
				"yellow": self._intreabaDeconectare,
				"blue": self._alteOptiuni,
			}, -2)

		self._campuri = [config.plugins.hdswebcontrol.activ, config.plugins.hdswebcontrol.port,
			config.plugins.hdswebcontrol.cod_retea_locala, config.plugins.hdswebcontrol.aplicatii,
			config.plugins.hdswebcontrol.aplicatii_afara]
		self._initiale = [c.value for c in self._campuri]
		self.list = [
			getConfigListEntry(_("Activează HdsWebControl"), config.plugins.hdswebcontrol.activ),
			getConfigListEntry(_("Port TCP"), config.plugins.hdswebcontrol.port),
			getConfigListEntry(_("Cere codul și în rețeaua locală"), config.plugins.hdswebcontrol.cod_retea_locala),
			getConfigListEntry(_("Aplicații de telefon"), config.plugins.hdswebcontrol.aplicatii),
			getConfigListEntry(_("Acces din afara casei"), config.plugins.hdswebcontrol.aplicatii_afara),
		]
		self["config"].list = self.list

		self._actualizeazaGhid()
		self._actualizeazaBrowsere()
		self._actualizeazaTextJeton()
		getattr(self, "onLayoutFinish", []).append(self._tasteMarite)

	def _tasteMarite(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): tastele colorate impart randul dupa
		textele lor, fiecare pe un rand (la 125 % "Deconecteaza browserele" trecea pe doua randuri). La 100 % nu se
		schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			if getattr(self, "parsedSkin", None) is None:
				# forma din skinul HDSatelit (skin.xml): randul tastelor e al cadrului, care il are loc si la textul
				# marit; impartirea ar muta numai textele, nu si barele colorate ale cadrului
				return
			taste = []
			for k in ("key_red", "key_green", "key_yellow", "key_blue"):
				for r in getattr(self, "renderer", ()):
					if getattr(r, "source", None) is self[k] and getattr(r, "instance", None) is not None:
						taste.append((r.instance, self[k].getText()))
			MT.imparteRandul(MT.Asezare(self), taste)
		except Exception as e:
			print("[HdsWebControlSetup] textul marit: %s" % e)

	def _actualizeazaGhid(self):
		"""Textul de sub setari, dupa randul „Cere codul și în rețeaua locală” (se schimba odata cu el)."""
		cere_cod = config.plugins.hdswebcontrol.cod_retea_locala.value
		if self._adresa and cere_cod:
			ghid = _("Deschide în browser adresa %s. Prima dată, pe televizor apare un cod de 6 cifre, pe care îl "
				"scrii în browser. Activarea și portul se aplică după repornirea interfeței.") % self._adresa
		elif self._adresa:
			ghid = _("Deschide în browser adresa %s. Din rețeaua locală nu se cere niciun cod. Activarea și portul "
				"se aplică după repornirea interfeței.") % self._adresa
		elif cere_cod:
			ghid = _("Deschide în browser adresa receptorului, cu portul de mai sus. Prima dată, pe televizor apare un "
				"cod de 6 cifre, pe care îl scrii în browser. Activarea și portul se aplică după repornirea interfeței.")
		else:
			ghid = _("Deschide în browser adresa receptorului, cu portul de mai sus. Din rețeaua locală nu se cere "
				"niciun cod. Activarea și portul se aplică după repornirea interfeței.")
		self["ghid"].setText(ghid)
		self._actualizeazaAplicatii()

	# ------------------------------------------------------------------ aplicatiile de telefon (aplicatii_web.py)
	def _actualizeazaAplicatii(self):
		"""Eticheta de sub cheia pentru scripturi, dupa randurile „Aplicații de telefon” si „Acces din afara casei”:
		pornit, ce scrii in aplicatie din casa (numai adresa) si din afara (root si parola pentru aplicatii, facuta acum,
		prima data) si aplicatiile conectate; oprit, la ce foloseste randul."""
		if not config.plugins.hdswebcontrol.aplicatii.value:
			self["aplicatii"].setText(_("Aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, "
				"înregistrări) primesc răspuns după ce pornești rândul de mai sus."))
			return
		try:
			parola = aplicatii_web.parola()
			vazute = aplicatii_web.vazute()
		except Exception as eroare:
			print("[HdsWebControlSetup] parola pentru aplicatii: %s" % eroare)
			parola, vazute = "?", []
		if config.plugins.hdswebcontrol.cod_retea_locala.value:
			# cu codul cerut si in casa, aplicatiile cer parola si acasa (aplicatii_web._poarta)
			randuri = [_("Aplicații de telefon: și acasă scrii utilizatorul root și parola %s (se cere codul și în "
				"casă).") % parola]
		else:
			randuri = [_("Aplicații de telefon: acasă scrii în aplicație numai adresa receptorului, fără utilizator și "
				"parolă.")]
		if config.plugins.hdswebcontrol.aplicatii_afara.value:
			randuri.append(_("Din afara casei: utilizatorul root și parola %s.") % parola)
		else:
			randuri.append(_("Din afara casei: oprit (rândul de mai sus). Pornit, cere utilizatorul root și parola %s.")
				% parola)
		if vazute:
			nume = ["%s (%s)" % (_(v["nume"]), v["adresa"]) for v in vazute[-_APLICATII_PE_ECRAN:]]
			randuri.append(_("Conectate: %s") % ", ".join(nume))
		self["aplicatii"].setText("\n".join(randuri))

	def _parolaNouaAplicatii(self, raspuns=True):
		if not raspuns:
			return
		aplicatii_web.parolaNoua()
		self._actualizeazaAplicatii()

	# ------------------------------------------------------------------ browserele conectate
	def _actualizeazaBrowsere(self):
		try:
			lista = obtineAsociere().listaBrowsere()
		except Exception as eroare:
			print("[HdsWebControlSetup] lista browserelor: %s" % eroare)
			lista = []
		# aceeasi lista pentru browsere si pentru viitoarea aplicatie de telefon (campul `tip`, asociere.py)
		self._are_aplicatii = any(b.get("tip") == "aplicatie" for b in lista)
		if not lista:
			self["browsere"].setText(_("Niciun browser conectat."))
			return
		if self._are_aplicatii:
			randuri = [_("Browsere și telefoane conectate (%d):") % len(lista)]
		else:
			randuri = [_("Browsere conectate (%d):") % len(lista)]
		for b in lista[:_BROWSERE_PE_ECRAN]:
			rand = b.get("nume", "Browser")
			if b.get("tip") == "aplicatie":
				rand = _("Telefon: %s") % rand
			if b.get("adresa"):
				rand += ", " + b["adresa"]
			rand += ", " + _("din %s") % time.strftime("%d.%m.%Y", time.localtime(b.get("creat", 0)))
			randuri.append("  " + rand)
		if len(lista) > _BROWSERE_PE_ECRAN:
			randuri.append("  " + _("și încă %d") % (len(lista) - _BROWSERE_PE_ECRAN))
		self["browsere"].setText("\n".join(randuri))

	def _intreabaDeconectare(self):
		from Screens.MessageBox import MessageBox
		if self._are_aplicatii:
			intrebare = _("Deconectezi toate browserele și telefoanele? Fiecare va avea nevoie din nou de un cod de pe televizor.")
		else:
			intrebare = _("Deconectezi toate browserele? Fiecare va avea nevoie din nou de un cod de pe televizor.")
		self.session.openWithCallback(self._deconecteazaToate, MessageBox, intrebare, MessageBox.TYPE_YESNO, default=False)

	def _deconecteazaToate(self, raspuns):
		if not raspuns:
			return
		numar = obtineAsociere().deconecteazaToate()
		print("[HdsWebControlSetup] browsere deconectate: %d" % numar)
		self._actualizeazaBrowsere()

	# ------------------------------------------------------------------ cheia pentru scripturi
	def _actualizeazaTextJeton(self):
		# cererile scripturilor catre /api/... au nevoie de aceasta cheie
		# (parametrul token=); afisata aici ca programatorul s-o poata copia. Browserul obisnuit nu are nevoie de ea.
		self["jeton"].setText(_("Cheie pentru scripturi (doar pentru programatori): %s") % config.plugins.hdswebcontrol.token.value)

	def _alteOptiuni(self):
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self._optiuneAleasa, ChoiceBox, title=_("Alte opțiuni"), list=[
			(_("Conectează un browser nou"), "browser_nou"),
			(_("Cheie nouă pentru panoul web"), "cheie"),
			(_("Parolă nouă pentru aplicații"), "parola_aplicatii"),
		])

	def _optiuneAleasa(self, alegere):
		if not alegere:
			return
		if alegere[1] == "browser_nou":
			self._conecteazaBrowserNou()
		elif alegere[1] == "cheie":
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(self._regenereazaJeton, MessageBox,
				_("Faci o cheie nouă pentru panoul web? Cheia veche nu mai merge, iar toate telefoanele și browserele "
				"asociate vor trebui asociate din nou."), MessageBox.TYPE_YESNO, default=False)
		elif alegere[1] == "parola_aplicatii":
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(self._parolaNouaAplicatii, MessageBox,
				_("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche nu mai "
				"primesc răspuns până nu scrii în ele parola nouă."), MessageBox.TYPE_YESNO, default=False)

	def _conecteazaBrowserNou(self):
		"""Din telecomanda, deci de la cine sta in fata televizorului: scoate blocarea dupa coduri gresite si
		limita de afisari, face un cod nou si il arata aici, in fereastra codului (HdsCodAsociere, aceeasi ca pentru
		codul cerut din browser). Pagina din browser ia apoi acelasi cod (un singur cod activ), fara alta fereastra
		pe televizor. Fereastra se inchide singura cand browserul se conecteaza."""
		from Screens.MessageBox import MessageBox
		from Screens.HdsCodAsociere import HdsCodAsociere
		asociere = obtineAsociere()
		asociere.deblocheaza()
		r = asociere.cereCod(tip="browser")
		if not r.get("cod"):
			# nu se intampla dupa deblocheaza(); daca totusi, omul afla de ce
			self.session.open(MessageBox, _("Codul nu a putut fi făcut acum. Încearcă din nou peste un minut."),
				MessageBox.TYPE_ERROR, timeout=10)
			return
		id_cerere = r.get("id_cerere")
		print("[HdsWebControlSetup] asocierea deblocata din telecomanda, cod nou pe ecran")
		self.session.openWithCallback(self._dupaCodNou, HdsCodAsociere, cod=r["cod"], tip="browser",
			adresaWeb=adresaWeb() or _("adresa receptorului"), expira=time.monotonic() + int(r["ramas"]),
			activ=lambda: asociere.codActiv(id_cerere), anuleaza=lambda: asociere.anuleazaCod(id_cerere))

	def _dupaCodNou(self, rezultat=None):
		self._actualizeazaBrowsere()
		if rezultat == "expirat":
			from Screens.MessageBox import MessageBox
			from Plugins.Extensions.HdsWebControl.plugin import textExpirare
			self.session.open(MessageBox, textExpirare(), MessageBox.TYPE_INFO, timeout=15)

	def _regenereazaJeton(self, raspuns=True):
		if not raspuns:
			return
		# aceeasi cheie noua ca in pagina web /interfata-web (HdsWebControl/internet_web.py): cheia si toate aparatele
		# asociate; de la televizor nu ramane niciunul. Cheia nu se scrie in jurnal.
		from Plugins.Extensions.HdsWebControl.internet_web import cheieNouaPanou
		numar = cheieNouaPanou(config, configfile, obtineAsociere())
		print("[HdsWebControlSetup] cheie noua pentru panoul web; aparate deconectate: %d" % numar)
		self._actualizeazaTextJeton()
		self._actualizeazaBrowsere()
		from Screens.MessageBox import MessageBox
		if config.plugins.hdswebcontrol.cod_retea_locala.value:
			mesaj = _("Cheia nouă pentru panoul web e făcută. Fiecare telefon și browser cere din nou codul de pe "
				"televizor: Albastru, apoi Conectează un browser nou.")
		else:
			mesaj = _("Cheia nouă pentru panoul web e făcută. Din rețeaua locală, telefoanele și browserele intră din nou "
				"fără cod, ca până acum.")
		self.session.open(MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=20)

	def salveaza(self):
		for c in self._campuri:
			c.save()
		self.close(True)

	def anuleaza(self):
		for c, valoare in zip(self._campuri, self._initiale):
			c.value = valoare
		self.close(False)
