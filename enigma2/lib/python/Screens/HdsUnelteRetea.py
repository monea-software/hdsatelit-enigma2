# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsUnelteRetea.py: utilitarele de retea de pe televizor (din 0.4.4), Meniu > Setari > Retea si Internet:
#   - HdsWifiCanaleScreen: "Cat de aglomerat e Wi-Fi-ul" (Components/HdsWifiCanale.py): graficul canalelor 1-13, canalul
#     recomandat pentru router si de ce, retelele cele mai tari; Galben: toate retelele gasite;
#   - HdsAparateReteaScreen: "Ce aparate sunt in retea" (Components/HdsAparateRetea.py): numele, adresa, producatorul si
#     adresa fizica a fiecarui aparat; Galben: ordinea dupa adresa sau dupa nume; OK: pagina web a aparatului in
#     navigatorul receptorului (http://adresa/, sau https:// cand numai acolo raspunde; HdsAparateRetea.adresa_web).
# Aceleasi date in interfata web: HdsWebControl/unelte_retea_web.py (/wifi-canale, /aparate-retea).
# Designul: ecranul Stitch "Ce aparate sunt in retea" (proiectul HD Satelit, sistemul HD Satelit Control) si culorile
# aceluiasi sistem pentru grafic. Skinul e in cod, cu resolution="1920,1080" (merge in orice skin). Cardurile (eLabel)
# se fac dupa widgeturile cu nume, deci widgeturile au zPosition="1", ca sa nu fie acoperite.

import threading

from enigma import eListboxPythonMultiContent, eTimer, getDesktop, gRGB, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.ProgressBar import ProgressBar
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsAparateRetea as A
from Components import HdsWifiCanale as W
from Components import HdsMarireText as MT
from Screens.Screen import Screen

CULOARE_NIVEL = {W.LIBER: 0x4FD18B, W.AGLOMERAT: 0xF1C40F, W.FOARTE: 0xFF6B5E}
CITIRE_MS = 500


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def _fontHds(nume):
	"""fontul HD Satelit cu rolul `nume` sub un skin strain (skin.fontHds); cu HDSatelit ales, `nume`"""
	try:
		import skin
		return skin.fontHds(nume)
	except Exception:
		return nume


# Inaltimile de mai jos sunt pentru marimea textului 130% (config.osd.fontscale; skin.py inmulteste
# fontul, nu si caseta): un rand HdsRegular are ~1,36 x marimea, deci tastele (28 -> 36) cer 50 px, titlul (44 -> 57) 78,
# cifrele canalelor (34 -> 44) 61, numarul retelelor (24 -> 31) 44. Inainte, la 130%, se taiau titlul, cifrele, etichetele
# "recomandat" (ru "рекомендуется" are 171 px la 23) si ultima retea de jos.
_TASTE = """
		<widget zPosition="1" source="key_red" render="Label" position="80,998" size="300,54" font="Regular;28" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00B3261E" />
		<widget zPosition="1" source="key_green" render="Label" position="400,998" size="300,54" font="Regular;28" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00137A44" />
		<widget zPosition="1" source="key_yellow" render="Label" position="720,998" size="360,54" font="Regular;28" halign="center" valign="center" foregroundColor="#000B1020" backgroundColor="#00E0B000" />"""


def _bare():
	rez = []
	for i in range(13):
		x = 90 + i * 90
		rez.append('<widget zPosition="1" name="tag%d" position="%d,180" size="176,38" font="Regular;18" halign="center" valign="center" noWrap="1" '
			'foregroundColor="#00B7C4FF" backgroundColor="#0010162A" transparent="1" />' % (i + 1, x - 60))
		rez.append('<widget zPosition="1" name="bara%d" position="%d,222" size="56,374" orientation="orBottomToTop" borderWidth="0" '
			'foregroundColor="#004FD18B" backgroundColor="#00161F3B" />' % (i + 1, x))
		rez.append('<widget zPosition="1" name="canal%d" position="%d,600" size="90,62" font="Regular;34" halign="center" valign="center" '
			'foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" />' % (i + 1, x - 17))
		rez.append('<widget zPosition="1" name="numar%d" position="%d,664" size="90,46" font="Regular;24" halign="center" valign="center" '
			'foregroundColor="#00AEB9CC" backgroundColor="#0010162A" transparent="1" />' % (i + 1, x - 17))
	return "\n\t\t".join(rez)


class HdsWifiCanaleScreen(Screen):
	# Recomandarea: caseta din dreapta tine toata inaltimea (160-984), iar textul e un ScrollLabel de
	# 640 px (pagini cu Sus / Jos, bara numai cand nu incape): cele 4 fraze au ~470 px la marimea textului 100% si 560-640 la
	# 115% (cat avea caseta veche, 430 px, deci se taiau), la 130% pana la ~870 in germana. Retelele de jos stau sub grafic.
	skin = """
	<screen name="HdsWifiCanaleScreen" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000E1323" title="Cât de aglomerat e Wi-Fi-ul">
		<widget zPosition="1" name="titlu" position="80,20" size="1760,80" font="Regular;44" valign="center" noWrap="1" foregroundColor="#00F2F4F8" backgroundColor="#000E1323" transparent="1" />
		<widget zPosition="1" name="subtitlu" position="80,100" size="1760,54" font="Regular;28" valign="center" foregroundColor="#00AEB9CC" backgroundColor="#000E1323" transparent="1" />
		<eLabel position="60,160" size="1240,570" backgroundColor="#0010162A" />
		<eLabel position="60,744" size="1240,240" backgroundColor="#0010162A" />
		""" + _bare() + """
		<eLabel position="1320,160" size="520,824" backgroundColor="#0010162A" />
		<eLabel position="1320,160" size="520,3" backgroundColor="#00374EA1" />
		<widget zPosition="1" name="rec_titlu" position="1350,174" size="460,50" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="rec_canal" position="1350,226" size="460,96" font="Regular;64" foregroundColor="#004FD18B" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="rec_text" position="1340,330" size="490,640" font="Regular;26" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" scrollbarMode="showOnDemand" />
		<widget zPosition="1" name="retele" position="90,750" size="1190,232" font="Regular;26" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="5" name="lista" position="80,160" size="1760,820" font="Regular;28" foregroundColor="#00F2F4F8" backgroundColor="#000E1323" />
		""" + _TASTE + """
	</screen>"""

	def __init__(self, session, placa=None):
		Screen.__init__(self, session)
		self.placa = placa
		self.cautare = None
		self.rez = None
		self.toate = False
		self["titlu"] = Label(_("Cât de aglomerat e Wi-Fi-ul"))
		self["subtitlu"] = Label(_("Se caută rețelele Wi-Fi..."))
		for i in range(1, 14):
			self["tag%d" % i] = Label("")
			self["bara%d" % i] = ProgressBar()
			self["canal%d" % i] = Label(str(i))
			self["numar%d" % i] = Label("")
		self["rec_titlu"] = Label(_("Recomandare"))
		self["rec_canal"] = Label("")
		self["rec_text"] = ScrollLabel("")
		self["retele"] = Label("")
		self["lista"] = ScrollLabel("")
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_("Caută din nou"))
		self["key_yellow"] = StaticText(_("Toate rețelele"))
		# sagetile dau pagina textului vazut: lista tuturor retelelor (Galben) sau recomandarea (graficul)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.close,
			"cancel": self.close,
			"red": self.close,
			"green": self.cauta,
			"yellow": self.comuta,
			"up": self.paginaSus,
			"down": self.paginaJos,
			"left": self.paginaSus,
			"right": self.paginaJos,
			"upRepeated": self.paginaSus,
			"downRepeated": self.paginaJos,
			"leftRepeated": self.paginaSus,
			"rightRepeated": self.paginaJos,
			# eliberarea sagetii: fara efect, ca jurnalul sa nu scrie "unknown action" la fiecare apasare
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self.onLayoutFinish.append(self.pornit)
		self.onClose.append(self.inchis)

	def pornit(self):
		self.setTitle(_("Cât de aglomerat e Wi-Fi-ul"))
		self["lista"].hide()
		if self.placa is None:
			placi = W.placi_wifi()
			self.placa = placi[0] if placi else None
		if self.placa is None:
			self["subtitlu"].setText(_("Receptorul nu are o placă Wi-Fi. Pune una în portul USB și deschide din nou."))
			return
		vechi = W.ultima()
		if vechi is not None and vechi.get("placa") == self.placa:
			self.arata(vechi)
		self.cauta()

	def inchis(self):
		if self.cautare is not None:
			self.cautare.opreste()

	def cauta(self):
		if self.placa is None:
			return
		if self.cautare is not None:
			self.cautare.opreste()
		self["subtitlu"].setText(_("Se caută rețelele Wi-Fi..."))
		self.cautare = W.Cautare(self.placa, self.gata)
		self.cautare.porneste()

	def gata(self, rez):
		if rez.get("stare") != "gata":
			self["subtitlu"].setText(rez.get("mesaj") or _("Căutarea rețelelor n-a reușit. Încearcă din nou."))
			return
		self.arata(rez)

	def arata(self, rez):
		self.rez = rez
		sub = _("Rețele găsite pe 2,4 GHz: %d") % rez["numar"]
		sub += " · " + _("placa Wi-Fi a receptorului recepționează numai 2,4 GHz")
		self["subtitlu"].setText(sub)
		for c in rez["canale"]:
			i = c["canal"]
			b = self["bara%d" % i]
			b.setValue(max(2, c["procent"]))
			try:
				b.instance.setForegroundColor(gRGB(CULOARE_NIVEL.get(c["nivel"], 0x4FD18B)))
			except Exception:
				pass
			self["numar%d" % i].setText(str(c["retele"]))
			try:
				# canalul recomandat cu cifra verde, celelalte albe
				self["canal%d" % i].instance.setForegroundColor(gRGB(0x4FD18B if c["recomandat"] else 0xF2F4F8))
			except Exception:
				pass
			tag = ""
			if c["recomandat"]:
				tag = _("recomandat")
			elif c["al_meu"]:
				tag = _("routerul tău")
			self["tag%d" % i].setText(tag)
			try:
				self["tag%d" % i].instance.setForegroundColor(gRGB(0x4FD18B if c["recomandat"] else 0xB7C4FF))
			except Exception:
				pass
		self["rec_canal"].setText(_("Canalul %d") % rez["recomandat"])
		self["rec_text"].setText("\n".join(rez["explicatie"]))
		randuri = []
		for r in rez["retele"][:5]:
			randuri.append("%s   ·   %s   ·   %s%s" % (r["nume"], (_("canalul %d") % r["canal"]) if r["canal"] else
				r["banda"] + " GHz", r["semnal"], ("   ·   " + _("a ta")) if r["a_mea"] else ""))
		self["retele"].setText("\n".join(randuri))
		self["lista"].setText(self.text_toate(rez))

	def text_toate(self, rez):
		randuri = [_("Toate rețelele găsite (%d)") % len(rez["retele"]), ""]
		for r in rez["retele"]:
			loc = (_("canalul %d") % r["canal"]) if r["canal"] else (r["banda"] + " GHz" if r["banda"] else "")
			d = ("%d dBm" % r["dbm"]) if r["dbm"] is not None else ""
			randuri.append("%s   ·   %s   ·   %s %s%s" % (r["nume"], loc, r["semnal"], d,
				("   ·   " + _("a ta")) if r["a_mea"] else ""))
		return "\n".join(randuri)

	def _nimic(self):
		pass

	def _textVazut(self):
		return self["lista"] if self.toate else self["rec_text"]

	def paginaSus(self):
		self._textVazut().pageUp()

	def paginaJos(self):
		self._textVazut().pageDown()

	def comuta(self):
		# lista tuturor retelelor (ScrollLabel) se strange la randuri intregi, deci sub ea ramane o fasie: retelele de jos si
		# recomandarea se ascund cat se vede lista, altfel un rand al lor se vedea sub ea. La fel graficul: eticheta
		# canalului 1 ("recomandat", "routerul tau") incepe la x=30, inaintea listei (x=80), iar capatul ei ramanea
		# descoperit langa lista (cu textul marit se vedea "re")
		self.toate = not self.toate
		grafic = ["retele", "rec_text"] + ["%s%d" % (n, i) for i in range(1, 14) for n in ("tag", "bara", "canal", "numar")]
		if self.toate:
			self["lista"].show()
			for n in grafic:
				self[n].hide()
			self["key_yellow"].setText(_("Graficul"))
		else:
			self["lista"].hide()
			for n in grafic:
				self[n].show()
			self["key_yellow"].setText(_("Toate rețelele"))


class HdsAparateReteaScreen(Screen):
	skin = """
	<screen name="HdsAparateReteaScreen" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000E1323" title="Ce aparate sunt în rețea">
		<widget zPosition="1" name="titlu" position="80,40" size="1760,60" font="Regular;44" foregroundColor="#00F2F4F8" backgroundColor="#000E1323" transparent="1" />
		<widget zPosition="1" name="subtitlu" position="80,104" size="1760,40" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#000E1323" transparent="1" />
		<eLabel position="80,160" size="1240,2" backgroundColor="#00374EA1" />
		<widget zPosition="1" name="lista" position="80,170" size="1240,810" scrollbarMode="showOnDemand" backgroundColor="#000E1323" foregroundColor="#00F2F4F8" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" transparent="1" />
		<eLabel position="1360,160" size="480,560" backgroundColor="#0010162A" />
		<eLabel position="1360,160" size="480,3" backgroundColor="#00374EA1" />
		<widget zPosition="1" name="cum_titlu" position="1384,180" size="432,40" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="cum" position="1384,226" size="432,480" font="Regular;24" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="detalii" position="1360,740" size="480,240" font="Regular;24" foregroundColor="#00C9D2E3" backgroundColor="#000E1323" transparent="1" />
		""" + _TASTE + """
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.dupa_nume = False
		self.aparate = []
		self.ceas = eTimer()
		self.ceas.callback.append(self.citeste)
		self["titlu"] = Label(_("Ce aparate sunt în rețea"))
		self["subtitlu"] = Label(_("Se caută aparatele din rețea..."))
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["cum_titlu"] = Label(_("Cum se află"))
		self["cum"] = Label(_("Din tabela de vecini a receptorului și o întrebare scurtă trimisă fiecărei adrese din "
			"rețeaua ta (fără căutări de porturi). Numele vin din răspunsurile aparatelor și de la router, producătorul "
			"din lista publică a adreselor MAC. Nimic nu pleacă în afara rețelei tale.\nTelefoanele adormite pot lipsi: "
			"caută din nou peste un minut."))
		self["detalii"] = Label("")
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_("Caută din nou"))
		self["key_yellow"] = StaticText(_("Ordinea: după nume"))
		self.textSub = ""
		self.rezWeb = None
		self.cautWeb = False
		self.ceasWeb = eTimer()
		self.ceasWeb.callback.append(self.webGata)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.deschide,
			"cancel": self.close,
			"red": self.close,
			"green": self.cauta,
			"yellow": self.ordine,
			"up": self.sus,
			"down": self.jos,
			"left": self["lista"].pageUp,
			"right": self["lista"].pageDown,
		}, -1)
		self.onLayoutFinish.append(self.pornit)
		self.onClose.append(self.ceas.stop)
		self.onClose.append(self.ceasWeb.stop)

	def pornit(self):
		self.setTitle(_("Ce aparate sunt în rețea"))
		f = _factor()
		self.f = f
		l = self["lista"].l
		# fonturile randurilor sunt puse din cod: urmeaza Marimea textului (Components/HdsMarireText), iar cu textul marit
		# randul si casetele lui cresc odata cu ele (_y; la 100 % aceleasi numere)
		l.setFont(0, MT.fontCod(_fontHds("Regular"), int(30 * f)))
		l.setFont(1, MT.fontCod(_fontHds("Regular"), int(22 * f)))
		l.setItemHeight(self._y(78))
		MT.randuriCod(self["lista"], self._y(78))
		self._textMarit()
		self.cauta()

	def _y(self, v):
		"""o inaltime a randului listei (scrisa pe 1920), pe ecranul de acum si crescuta cu textul marit"""
		return MT.inaltimeCod(int(v * self.f))

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): titlul urca si creste cat randul fontului
		(cozile literelor se taiau de la 110 %), subtitlul la fel sub el; caseta "Cum se afla" creste in jos cat ii cere
		textul (de la 125 % se pierdea ultimul rand), cu panoul ei, iar detaliile de dedesubt coboara si se scurteaza.
		La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			t, s = self["titlu"].instance, self["subtitlu"].instance
			skT, skS = a.dinSkin(t), a.dinSkin(s)
			if skT and skS:
				nT, nS = MT.marimeFont(t) * 140 // 100, MT.marimeFont(s) * 140 // 100
				sus = min(20, max(0, nT - skT[3]))
				a.pune(t, skT[0], skT[1] - sus, skT[2], max(skT[3], nT))
				yS = max(skS[1], skT[1] - sus + max(skT[3], nT) + 4)
				a.pune(s, skS[0], yS, skS[2], max(skS[3], nS))
			cum, det = self["cum"].instance, self["detalii"].instance
			skC, skD, panou = a.dinSkin(cum), a.dinSkin(det), a.cuprinde(cum)
			if skC and skD:
				d = a.creste(cum, MT.inaltimeText(cum), skD[1] + skD[3], maxim=skD[3] // 2)
				if d and panou:
					for e in a.elemente:
						if e[1:5] == panou:
							a.pune(e[0], panou[0], panou[1], panou[2], panou[3] + d)
		except Exception as e:
			print("[HdsAparateRetea] textul marit: %s" % e)

	def cauta(self):
		ok, motiv = A.porneste()
		if not ok and motiv and not A.cautare().lucreaza():
			self["subtitlu"].setText(motiv)
		self.ceas.start(CITIRE_MS, False)
		self.citeste()

	def citeste(self):
		st = A.rezultat()
		if st["stare"] == "lucreaza":
			self["subtitlu"].setText(st.get("faza") or _("Se caută aparatele din rețea..."))
			return
		self.ceas.stop()
		if st["stare"] == "eroare":
			self["subtitlu"].setText(st.get("mesaj", ""))
			return
		if st["stare"] != "gata":
			return
		self.aparate = st["aparate"]
		sub = _("Rețeaua %s · %d aparate găsite · nimic nu pleacă în afara rețelei tale") % (st["retea"], len(self.aparate))
		if st.get("mesaj"):
			sub = st["mesaj"]
		self.textSub = sub
		self["subtitlu"].setText(sub)
		self.umple()

	def umple(self):
		ap = list(self.aparate)
		if self.dupa_nume:
			ap.sort(key=lambda a: ((a["nume"] or "~").lower(), A.ip_num(a["ip"])))
		f = self.f
		try:
			w = self["lista"].instance.size().width()
		except Exception:
			w = int(1240 * f)
		h, y = self._y(78), self._y
		randuri = []
		for a in ap:
			nume = a["nume"] or _("fără nume")
			eticheta = A.text_eticheta(a["eticheta"])
			randuri.append([a,
				MultiContentEntryText(pos=(int(12 * f), 0), size=(int(420 * f), y(44)), font=0,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=nume),
				MultiContentEntryText(pos=(int(12 * f), y(44)), size=(int(420 * f), y(30)), font=1,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=eticheta, color=0xB7C4FF),
				MultiContentEntryText(pos=(int(440 * f), 0), size=(int(240 * f), h), font=0,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=a["ip"]),
				# in lista, adresa aleatoare pe scurt (textul intreg e in detaliile din dreapta)
				MultiContentEntryText(pos=(int(690 * f), 0), size=(w - int(700 * f), y(44)), font=0,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=_("Adresă aleatoare") if A.mac_aleatoare(a["mac"]) and
					a["producator"] == A.text_producator(a["mac"], None) else a["producator"]),
				MultiContentEntryText(pos=(int(690 * f), y(44)), size=(w - int(700 * f), y(30)), font=1,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=a["mac"].upper(), color=0xAEB9CC),
			])
		self["lista"].setList(randuri)
		self.detalii()

	def detalii(self):
		c = self["lista"].getCurrent()
		if not c:
			self["detalii"].setText("")
			return
		a = c[0]
		linii = [a["nume"] or _("fără nume"), a["ip"], a["mac"].upper(), a["producator"]]
		sursa = {"mdns": _("numele dat de aparat (mDNS)"), "netbios": _("numele de calculator (NetBIOS)"),
			"dns": _("numele știut de router"), "receptor": _("numele receptorului")}.get(a["sursa_nume"], "")
		if sursa:
			linii.append(sursa)
		linii.append(_("OK: pagina web a aparatului, în navigator."))
		self["detalii"].setText("\n".join(linii))

	def deschide(self):
		"""OK pe un aparat: pagina lui web in navigatorul receptorului. Porturile 80 / 443 se incearca pe un fir (cel mult
		doua conectari cu termen), raspunsul se citeste pe firul enigma2 (ceasWeb)."""
		c = self["lista"].getCurrent()
		if not c or self.cautWeb:
			return
		ip = c[0]["ip"]
		self.cautWeb = True
		self.rezWeb = None
		self["subtitlu"].setText(_("Caut pagina web a aparatului %s...") % ip)

		def merge():
			try:
				adresa = A.adresa_web(ip)
			except Exception as e:
				print("[HdsAparateRetea] pagina web: %r" % (e,))
				adresa = ""
			self.rezWeb = (ip, adresa)
		fir = threading.Thread(target=merge)
		fir.daemon = True
		fir.start()
		self.ceasWeb.start(200, False)

	def webGata(self):
		if self.rezWeb is None:
			return
		self.ceasWeb.stop()
		ip, adresa = self.rezWeb
		self.rezWeb = None
		self.cautWeb = False
		self["subtitlu"].setText(self.textSub)
		from Screens.MessageBox import MessageBox
		if not adresa:
			self.session.open(MessageBox, _("Aparatul %s nu are o pagină web (nu răspunde pe portul 80 și nici pe 443).") % ip,
				MessageBox.TYPE_INFO, timeout=8)
			return
		try:
			from Plugins.Extensions.HdsNavigator.plugin import deschideNavigator
			deschideNavigator(self.session, adresa)
		except Exception as e:
			print("[HdsAparateRetea] navigatorul: %r" % (e,))
			self.session.open(MessageBox, _("Navigatorul web nu se poate deschide acum."), MessageBox.TYPE_ERROR, timeout=8)

	def sus(self):
		self["lista"].up()
		self.detalii()

	def jos(self):
		self["lista"].down()
		self.detalii()

	def ordine(self):
		self.dupa_nume = not self.dupa_nume
		self["key_yellow"].setText(_("Ordinea: după adresă") if self.dupa_nume else _("Ordinea: după nume"))
		self.umple()


def wifi_canale(session, **kwargs):
	session.open(HdsWifiCanaleScreen)


def aparate_retea(session, **kwargs):
	session.open(HdsAparateReteaScreen)
