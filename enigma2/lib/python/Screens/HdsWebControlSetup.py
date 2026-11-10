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
# ecranul arata adresa de deschis in browser si browserele intrate cu parola (cand omul si-a pus parola din reteaua de
# acasa pentru interfata web) si le poate deconecta pe toate (Galben, cu confirmare). Efectul e imediat, fara
# repornire: ecranul si serverul folosesc acelasi obiect (obtineAsociere(), acelasi proces).
# Cheia pentru scripturi (fostul "jeton") ramane, cu "Cheie nouă pentru panoul web" sub Albastru > Alte optiuni:
# cu confirmare, cheie noua si toate browserele intrate deconectate (internet_web.cheieNouaPanou, aceeasi ca in web).
#
# Codul de 6 cifre de pe televizor (fereastra HdsCodAsociere, "Conectează un browser nou", randul "Cere codul și în
# rețeaua locală") s-a scos de tot. Din casa se intra direct. Parola din reteaua de acasa (una singura, numai daca o
# vrea omul) se pune in Setari > Retea > Parola receptorului (Components/HdsParolaLocala.py); aici ghidul spune numai
# daca e ceruta.
#
# randul „Aplicații de telefon” (pornit din fabrica) tine pornite rutele pentru aplicatiile obisnuite ale receptoarelor
# Enigma2 (canale, telecomanda, ghid, inregistrari, liste m3u); din casa merg fara parola (cu parola omului bifata la
# interfata web, cu utilizatorul root si parola lui). Randul de sub el, „Acces din afara casei” (oprit din fabrica),
# le lasa sa raspunda si din afara retelei locale, numai cu utilizatorul root si parola pentru aplicatii (facuta de
# receptor, paza fata de internet). Albastru > Alte optiuni > „Parolă nouă pentru aplicații” o schimba.
#
# Parola pentru aplicatii si cheia pentru scripturi sunt facute de receptor (omul nu le scrie); se arata la cerere:
# Albastru > Alte optiuni > "Arată parola și cheia". Pana atunci randul spune ca nu se arata, fara steluțe sau puncte
# in locul lor. Si dupa schimbare se arata numai la cerere. Se ascund la iesirea din ecran sau dupa cinci minute.
# In web la fel: butoanele "Arată" din /setari si /interfata-web (POST /api/interfata-web-secrete).

import time
from enigma import eTimer

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
# in locul parolei si al cheiei, cat nu s-a cerut "Arată parola și cheia" (un text, nu puncte)
def _neaaratata():
	return _("(se arată din Albastru > Alte opțiuni)")


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
		# parola pentru aplicatii si cheia pentru scripturi: ascunse la fiecare deschidere
		self._arata = False
		self._dialogPropriu = 0
		self._ceasArata = eTimer()
		self._ceasArata.callback.append(self._ascundeSecrete)
		if not hasattr(self, "onHide"):
			self.onHide = []
		self.onHide.append(self._laAscundere)
		self.onClose.append(self._ascundeSecrete)
		self["ghid"] = StaticText("")
		self["browsere"] = StaticText("")
		self["jeton"] = StaticText("")
		self["aplicatii"] = StaticText("")
		self["jeton"].hdsSecret = True
		self["aplicatii"].hdsSecret = True
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
			config.plugins.hdswebcontrol.aplicatii,
			config.plugins.hdswebcontrol.aplicatii_afara]
		self._initiale = [c.value for c in self._campuri]
		self.list = [
			getConfigListEntry(_("Activează HdsWebControl"), config.plugins.hdswebcontrol.activ),
			getConfigListEntry(_("Port TCP"), config.plugins.hdswebcontrol.port),
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

	def _parolaWeb(self):
		try:
			from Plugins.Extensions.HdsWebControl.plugin import parolaWebCeruta
			return parolaWebCeruta()
		except Exception as eroare:
			print("[HdsWebControlSetup] parola din reteaua de acasa: %s" % eroare)
			return False

	def _actualizeazaGhid(self):
		"""Textul de sub setari: adresa si daca in casa se cere parola omului (pusa in Parola receptorului)."""
		if self._parolaWeb():
			parola = _("Ai pus parolă pentru interfața web: browserul o cere o dată (o scoți în Setări > Rețea > "
				"Parola receptorului).")
		else:
			parola = _("Din rețeaua de acasă nu se cere nici cod, nici parolă.")
		if self._adresa:
			ghid = _("Deschide în browser adresa %s.") % self._adresa
		else:
			ghid = _("Deschide în browser adresa receptorului, cu portul de mai sus.")
		self["ghid"].setText("%s %s %s" % (ghid, parola, _("Activarea și portul se aplică după repornirea "
			"interfeței.")))
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
		if not self._arata:
			parola = _neaaratata()
		if self._parolaWeb():
			# cu parola omului bifata la interfata web, aplicatiile o cer si acasa (aplicatii_web._poarta)
			randuri = [_("Aplicații de telefon: și acasă scrii utilizatorul root și parola ta (pusă în Parola "
				"receptorului).")]
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
		self._ascundeSecrete()

	def _comutaArata(self):
		if self._arata:
			self._ascundeSecrete()
		else:
			self._arataSecrete()

	def _arataSecrete(self):
		self._arata = True
		self._ceasArata.start(5 * 60 * 1000, True)
		self._actualizeazaAplicatii()
		self._actualizeazaTextJeton()

	def _ascundeSecrete(self):
		self._ceasArata.stop()
		self._arata = False
		self._actualizeazaAplicatii()
		self._actualizeazaTextJeton()

	def _laAscundere(self):
		# Alte optiuni si confirmarile sunt ferestre ale acestui ecran. Cele cinci minute continua si acolo.
		if not self._dialogPropriu:
			self._ascundeSecrete()

	def _deschideDialog(self, callback, ecran, *args, **kwargs):
		self._dialogPropriu += 1
		def inchis(*raspuns):
			self._dialogPropriu = max(0, self._dialogPropriu - 1)
			if callback is not None:
				return callback(*raspuns)
		try:
			dialog = self.session.openWithCallback(inchis, ecran, *args, **kwargs)
		except Exception:
			self._dialogPropriu = max(0, self._dialogPropriu - 1)
			raise
		if dialog is None:
			self._dialogPropriu = max(0, self._dialogPropriu - 1)
		return dialog

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
			self["browsere"].setText(_("Niciun browser intrat cu parolă."))
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
			intrebare = _("Deconectezi toate browserele și telefoanele? Cu parola pusă, fiecare o cere din nou.")
		else:
			intrebare = _("Deconectezi toate browserele? Cu parola pusă, fiecare o cere din nou.")
		self._deschideDialog(self._deconecteazaToate, MessageBox, intrebare, MessageBox.TYPE_YESNO, default=False)

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
		cheie = config.plugins.hdswebcontrol.token.value if self._arata else _neaaratata()
		self["jeton"].setText(_("Cheie pentru scripturi (doar pentru programatori): %s") % cheie)

	def _alteOptiuni(self):
		from Screens.ChoiceBox import ChoiceBox
		self._deschideDialog(self._optiuneAleasa, ChoiceBox, title=_("Alte opțiuni"), list=[
			(_("Ascunde parola și cheia"), "ascunde") if self._arata else (_("Arată parola și cheia"), "arata"),
			(_("Cheie nouă pentru panoul web"), "cheie"),
			(_("Parolă nouă pentru aplicații"), "parola_aplicatii"),
		])

	def _optiuneAleasa(self, alegere):
		if not alegere:
			return
		if alegere[1] == "arata":
			self._arataSecrete()
		elif alegere[1] == "ascunde":
			self._ascundeSecrete()
		elif alegere[1] == "cheie":
			from Screens.MessageBox import MessageBox
			self._deschideDialog(self._regenereazaJeton, MessageBox,
				_("Faci o cheie nouă pentru panoul web? Cheia veche nu mai merge, iar browserele intrate cu parolă o "
				"cer din nou."), MessageBox.TYPE_YESNO, default=False)
		elif alegere[1] == "parola_aplicatii":
			from Screens.MessageBox import MessageBox
			self._deschideDialog(self._parolaNouaAplicatii, MessageBox,
				_("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche nu mai "
				"primesc răspuns până nu scrii în ele parola nouă."), MessageBox.TYPE_YESNO, default=False)

	def _regenereazaJeton(self, raspuns=True):
		if not raspuns:
			return
		# aceeasi cheie noua ca in pagina web /interfata-web (HdsWebControl/internet_web.py): cheia si toate aparatele
		# asociate; de la televizor nu ramane niciunul. Cheia nu se scrie in jurnal.
		from Plugins.Extensions.HdsWebControl.internet_web import cheieNouaPanou
		numar = cheieNouaPanou(config, configfile, obtineAsociere())
		print("[HdsWebControlSetup] cheie noua pentru panoul web; aparate deconectate: %d" % numar)
		self._ascundeSecrete()
		self._actualizeazaBrowsere()
		from Screens.MessageBox import MessageBox
		if self._parolaWeb():
			mesaj = _("Cheia nouă pentru panoul web e făcută. Fiecare browser cere din nou parola ta.")
		else:
			mesaj = _("Cheia nouă pentru panoul web e făcută. Din rețeaua locală, telefoanele și browserele intră "
				"direct, ca până acum.")
		self._deschideDialog(None, MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=20)

	def salveaza(self):
		for c in self._campuri:
			c.save()
		self.close(True)

	def anuleaza(self):
		for c, valoare in zip(self._campuri, self._initiale):
			c.value = valoare
		self.close(False)
