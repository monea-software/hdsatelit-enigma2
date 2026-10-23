# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsModSigur.py (ecranele): mesajul modului sigur si ecranul „Ce s-a întâmplat”. Logica, starea si textele sunt in
# Components/HdsModSigur.py (aceleasi in pagina web mod_sigur_web.py).
#
# HdsModSigur: primul ecran cand interfata a pornit in modul sigur (mytest.py il pune inaintea vrajitorilor si a
# InfoBar-ului), si din Meniu > Informații despre sistem > Mod sigur (se vede numai in modul sigur). De sus in jos:
# titlul, mesajul („Receptorul a căzut de mai multe ori la pornire. Am pornit în mod sigur.”), fraza cu numarul
# opririlor si extensiile oprite (primele nume, apoi „și încă N”), lista cu cele trei alegeri, descrierea alegerii de
# sub cursor si nota cu tastele si adresa paginii web. Sagetile aleg, OK face alegerea; EXIT inchide ecranul si
# interfata ramane in modul sigur. „Pornește normal” si „Pune înapoi setările de dinainte” scriu numai cererea
# (Components/HdsModSigur) si, dupa 1,5 s in care textul alegerii se vede, cer repornirea interfetei ca din meniu
# (TryQuitMainloop 3). Daca repornirea e refuzata (o inregistrare in curs), cererea se sterge si ecranul o spune. Un
# rand care nu se poate alege (fara copia setarilor) e gri si pe banda cursorului; OK pe el spune de ce.
#
# HdsModSigurDetalii: randurile pe grupe (opririle, ultima eroare, modul sigur cu cate un rand pe extensie oprita), cu
# eticheta la stanga si valoarea colorata dupa stare, pe aceeasi linie de baza (aliniate sus, cu acelasi decalaj);
# lamuririle tehnice pe randuri mai mici. Textul brut (jurnalul opririlor, rapoartele de eroare, numaratoarea) pe tasta
# ALBASTRA sau pe OK, citit pe un fir; Stanga/Dreapta intre fisiere, Sus/Jos derulare; EXIT inapoi. Titlul are numele
# scurt al fisierului si „(n/m)”, calea e prima linie a textului. Dintr-un raport se arata numai ultimele randuri ale
# jurnalului (Components/HdsModSigur.MAX_BRUT_RAPORT); fisierul intreg ramane pe disc.
#
# Skinurile: facute la deschidere dupa marimea ecranului (asezarea e gandita pe 1920x1080), numai cu fontul „Regular”
# si culori scrise direct, ca sa arate la fel in orice skin; culorile starilor se iau din skinul HDSatelit cand exista.

from enigma import eListboxPythonMultiContent, getDesktop, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsModSigur as M
from Components import HdsMarireText as MT

# lib/gdi/grc.h: alinierea verticala implicita (sus); cu ea textele de aceeasi marime stau pe aceeasi linie de baza
RT_VALIGN_TOP = 0

PAGINA_WEB = "/mod-sigur"
# cate litere incap in coloana valorilor (fontul Regular, 28 px la 1920)
MAX_VALOARE = 78
# cat se vede textul alegerii inainte de repornire
PAUZA_REPORNIRE_MS = 1500

# culorile din skinul HDSatelit si rezerva pentru alt skin (0xRRGGBB)
CULORI = {
	"titlu": ("hdsBrandLight", 0x9FB4FF),
	"eticheta": ("hdsLabel", 0xAEB9CC),
	M.NORMAL: ("hdsText", 0xF2F4F8),
	M.BUN: ("hdsGood", 0x4FD18B),
	M.ATENTIE: ("hdsAmber", 0xF5B83D),
	M.RAU: ("hdsBad", 0xFF6B5E),
	M.STINS: ("hdsDisabled", 0x8A94A6),
}
# randurile alegerilor: textul pe fundalul listei si pe banda aleasa (chihlimbar); randul care nu se poate alege are
# banda lui, gri, si textul deschis, ca sa nu arate ca o alegere buna cand cursorul e pe el
CULOARE_ALEGERE = 0xF2F4F8
CULOARE_ALEGERE_ALEASA = 0x101828
BANDA_STINSA = 0x3A4458
CULOARE_STINSA_ALEASA = 0xC9D2E3


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return implicit


def _scara(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	return x, y


def _scurt(text, maxim):
	text = text or ""
	return text if len(text) <= maxim else text[:maxim - 1].rstrip() + u"…"


def _sus(h, px):
	"""Decalajul de sus al unui text de `px` intr-un rand de `h`, ca textul sa stea la mijloc cu alinierea sus."""
	return max(0, (h - int(round(px * 1.2))) // 2)


def adresaWeb():
	"""http://<ip>[:port]/mod-sigur, sau "" cat timp receptorul nu are adresa in retea"""
	try:
		from Screens.HdsPazaModel import adresaIp, portWeb
		ip = adresaIp()
		port = portWeb()
	except Exception:
		return ""
	if not ip:
		return ""
	return "http://%s%s%s" % (ip, "" if port == 80 else ":%d" % port, PAGINA_WEB)


def textNota(adresa):
	taste = _("Săgețile aleg, OK confirmă. EXIT: rămâi în modul sigur; ecranul se deschide din nou din Meniu > "
		"Informații despre sistem > Mod sigur.")
	if adresa:
		return taste + "\n" + _("Aceleași alegeri sunt și în interfața web: %s") % adresa
	return taste + "\n" + _("Aceleași alegeri sunt și în interfața web, la pagina /mod-sigur.")


def skinEcran(latime, inaltime):
	"""Mesajul pe tot ecranul, socotit pentru `latime` x `inaltime` (asezarea pe 1920x1080). Fraza de sub mesaj are 4
	randuri (numarul opririlor, setarile puse inapoi singure, primele extensii oprite)."""
	x, y = _scara(latime, inaltime)
	return """
	<screen name="HdsModSigur" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#00101828" title="Mod sigur">
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<eLabel position="%(mx)d,%(ly)d" size="%(cl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="explicatie" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00d4dae4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="alegeri" position="%(mx)d,%(ay)d" size="%(al)d,%(ah)d" itemHeight="%(ai)d" backgroundColor="#00182236" backgroundColorSelected="#00f5b83d" scrollbarMode="showNever" transparent="0" zPosition="1" />
		<widget source="descriere" render="Label" position="%(mx)d,%(dy)d" size="%(cl)d,%(dh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(nf)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"l": latime, "h": inaltime, "mx": x(160), "cl": latime - 2 * x(160), "linie": max(2, y(4)),
		"ty": y(50), "th": y(80), "tf": y(56), "ly": y(140),
		"my": y(170), "mh": y(120), "mf": y(42),
		"ey": y(300), "eh": y(170), "ef": y(30),
		"ay": y(490), "ah": y(3 * 72), "al": x(980), "ai": y(72),
		"dy": y(730), "dh": y(150),
		"ny": y(930), "nh": y(110), "nf": y(26),
	}


def skinDetalii(latime, inaltime):
	"""„Ce s-a întâmplat” pe tot ecranul (asezarea pe 1920x1080): lista pe grupe si, in acelasi loc, textul brut."""
	x, y = _scara(latime, inaltime)
	return """
	<screen name="HdsModSigurDetalii" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#00101828" title="Ce s-a întâmplat">
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" noWrap="1" />
		<eLabel position="%(mx)d,%(ly)d" size="%(cl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget name="lista" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" itemHeight="%(ih)d" scrollbarMode="showOnDemand" backgroundColor="#00101828" backgroundColorSelected="#00101828" transparent="1" zPosition="2" />
		<widget name="brut" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(bf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="3" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(nl)d,%(nh)d" font="Regular;%(nf)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="key_blue" render="Label" position="%(bx)d,%(ny)d" size="%(bl)d,%(nh)d" font="Regular;%(nf)d" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#003d7be0" zPosition="1" />
	</screen>""" % {
		"l": latime, "h": inaltime, "mx": x(120), "cl": latime - 2 * x(120), "linie": max(2, y(4)),
		"ty": y(30), "th": y(70), "tf": y(46), "ly": y(108),
		"ey": y(130), "eh": y(820), "ih": MT.inaltimeCod(y(41)), "bf": y(27),
		"ny": y(985), "nh": y(56), "nf": y(26), "nl": latime - 2 * x(120) - x(320),
		"bx": latime - x(120) - x(290), "bl": x(290),
	}


class HdsModSigur(Screen):
	# standby opreste canalul; mytest.py PowerKey cere atributul pentru standby si oprire
	ALLOW_SUSPEND = Screen.SUSPEND_STOPS

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = skinEcran(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(M.titlu())
		self.stare = M.stare()
		self.optiuni = M.alegeri(self.stare)
		self["titlu"] = StaticText(M.titlu())
		self["mesaj"] = StaticText(M.textMesaj())
		self["explicatie"] = StaticText(M.textExplicatie(self.stare))
		self["alegeri"] = MenuList([], content=eListboxPythonMultiContent)
		self["descriere"] = StaticText(self.optiuni[0][2])
		self["nota"] = StaticText(textNota(adresaWeb()))
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.keyOk,
			"cancel": self.close,
			"up": self.keySus,
			"down": self.keyJos,
			"left": self.keySus,
			"right": self.keyJos,
			"upRepeated": self.keySus,
			"downRepeated": self.keyJos,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action”
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
			"leftRepeated": self._nimic,
			"rightRepeated": self._nimic,
		}, -1)
		# alegerea facuta, cat asteapta repornirea (tastele nu mai schimba nimic); None dupa un refuz
		self.aleasa = None
		self.inchis = False
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)
		print("[HdsModSigur] ecranul modului sigur; oprite: %s" % (", ".join(self.stare.get("oprite") or []) or "niciuna"))

	def _laInchidere(self):
		self.inchis = True

	def _pregateste(self):
		x, y = _scara(getDesktop(0).size().width(), getDesktop(0).size().height())
		lista = self["alegeri"]
		# fontul pus din cod urmeaza Marimea textului (Components/HdsMarireText); randul de 72 are loc si pentru litera de
		# la 130 % (46 px), iar ecranul e asezat pe tot televizorul (_textMarit), deci randul ramane
		lista.l.setFont(0, MT.fontCod("Regular", y(36)))
		lista.l.setItemHeight(y(72))
		try:
			w = lista.instance.size().width()
		except Exception:
			w = x(980)
		stins = _culoare(M.STINS)
		randuri = []
		for cheie, titlu, _desc, se_poate in self.optiuni:
			rand = [cheie]
			if not se_poate:
				# banda gri pe tot randul, peste banda chihlimbar a listei, numai cand cursorul e pe el
				rand.append(MultiContentEntryText(pos=(0, 0), size=(w, y(72)), font=0, text="", backcolor_sel=BANDA_STINSA))
			rand.append(MultiContentEntryText(pos=(x(28), 0), size=(w - x(56), y(72)), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=titlu, color=CULOARE_ALEGERE if se_poate else stins,
				color_sel=CULOARE_ALEGERE_ALEASA if se_poate else CULOARE_STINSA_ALEASA))
			randuri.append(rand)
		lista.setList(randuri)
		self._textMarit()

	def _eticheta(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return None

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): ecranul e asezat pe tot televizorul, fara
		loc liber, iar la 115 % se taia randul cu adresa web din nota, la 130 % si al doilea rand al mesajului. Titlul,
		mesajul, explicatia, alegerile, descrierea (cea mai lunga dintre ale alegerilor) si nota se pun una sub alta, fiecare
		cat ii cere textul, cu distantele dintre ele; cand nu incap pe ecran, fontul textelor scade cu cate un pixel (nu sub
		marimea de la 100 %) pana cand incap, deci niciun rand nu se pierde. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			titlu, mesaj, expl = self._eticheta("titlu"), self._eticheta("mesaj"), self._eticheta("explicatie")
			desc, nota = self._eticheta("descriere"), self._eticheta("nota")
			if None in (titlu, mesaj, expl, desc, nota):
				return
			# linia de sub titlu (eticheta fara nume din skin): coboara cu titlul
			linie = None
			for e in a.elemente:
				if e[4] <= 6 and e[3] > 100:
					linie = e[0]
			texteDesc = [o[2] for o in self.optiuni] + [M.textNuSePoate(self.stare)]

			def nevoieDesc():
				n = 0
				for text in texteDesc:
					desc.setText(text)
					n = max(n, MT.inaltimeText(desc))
				desc.setText(self["descriere"].getText())
				return n
			blocuri = [(titlu, lambda: MT.marimeFont(titlu) * 125 // 100), (linie, None),
				(mesaj, lambda: MT.inaltimeText(mesaj)), (expl, lambda: MT.inaltimeText(expl)),
				(self["alegeri"].instance, None), (desc, nevoieDesc), (nota, lambda: MT.inaltimeText(nota))]
			MT.potrivesteStiva(a, [b for b in blocuri if b[0] is not None], getDesktop(0).size().height() - 16,
				(mesaj, expl, desc, nota))
		except Exception as e:
			print("[HdsModSigur] textul marit: %s" % e)

	def _nimic(self):
		pass

	def _descriere(self):
		i = self["alegeri"].getSelectionIndex() or 0
		self["descriere"].setText(self.optiuni[i][2])

	def keySus(self):
		if self.aleasa is not None:
			return
		self["alegeri"].up()
		self._descriere()

	def keyJos(self):
		if self.aleasa is not None:
			return
		self["alegeri"].down()
		self._descriere()

	def keyOk(self):
		if self.aleasa is not None:
			return
		i = self["alegeri"].getSelectionIndex() or 0
		cheie, _titlu, _desc, se_poate = self.optiuni[i]
		if cheie == "detalii":
			self.session.open(HdsModSigurDetalii)
			return
		if not se_poate:
			# alt text decat descrierea de sub cursor: apasarea se vede
			self["descriere"].setText(M.textNuSePoate(self.stare))
			return
		if cheie == "normal":
			ok, text = M.pornesteNormal()
		else:
			ok, text = M.punInapoiSetarile()
		if not ok:
			self["descriere"].setText(text)
			return
		self.aleasa = cheie
		self["descriere"].setText(text + " " + _("Interfața se repornește."))
		M.reporneste(self.session, dupa_ms=PAUZA_REPORNIRE_MS, la_refuz=self._refuzata)

	def _refuzata(self):
		self.aleasa = None
		if not self.inchis:
			self["descriere"].setText(M.textRepornireRefuzata())


class HdsModSigurDetalii(Screen):
	ALLOW_SUSPEND = Screen.SUSPEND_STOPS

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = skinDetalii(marime.width(), marime.height())
		self.x, self.y = _scara(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.titluEcran = _("Ce s-a întâmplat")
		self.setTitle(self.titluEcran)
		self["titlu"] = StaticText(self.titluEcran)
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["brut"] = ScrollLabel("")
		self["nota"] = StaticText("")
		self["key_blue"] = StaticText(_("Text brut"))
		self.brutVizibil = False
		self.citeste = False
		self.inchis = False
		self.pagina = 0
		self.pagini = []
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.keyAlbastru,
			"blue": self.keyAlbastru,
			"cancel": self.close,
			"red": self.close,
			"up": self.keySus,
			"down": self.keyJos,
			"left": self.keyStanga,
			"right": self.keyDreapta,
			"upRepeated": self.keySus,
			"downRepeated": self.keyJos,
			# tinute apasat, Stanga/Dreapta nu sar peste fisiere; ridicarea tastei e legata fara efect
			"leftRepeated": self._nimic,
			"rightRepeated": self._nimic,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	def _laInchidere(self):
		self.inchis = True

	def _pregateste(self):
		y = self.y
		lista = self["lista"]
		# fonturile puse din cod urmeaza Marimea textului (Components/HdsMarireText); cu textul marit randul creste odata
		# cu ele (la 100 % aceleasi numere). self.fonturi tine marimile desenate, pentru linia de baza (_sus)
		baza = {0: y(30), 1: y(28), 2: y(26)}
		self.fonturi = dict((n, MT.marimeCod(px)) for n, px in baza.items())
		for n, px in baza.items():
			lista.l.setFont(n, MT.fontCod("Regular", px))
		self.rand = MT.inaltimeCod(y(41))
		lista.l.setItemHeight(self.rand)
		MT.randuriCod(lista, self.rand)
		try:
			self.latime = lista.instance.size().width()
		except Exception:
			self.latime = self.x(1680)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		lista.setList([self._intrare(r) for r in M.randuri(M.stare())])
		self["brut"].hide()
		self._nota()

	def _text(self, x, w, font, text, culoare):
		"""Un text al randului, aliniat sus cu decalajul fontului lui: textele de aceeasi marime au aceeasi linie de baza
		(RT_VALIGN_CENTER centreaza conturul literelor, deci „Î” sau „p” mutau textul in sus sau in jos)."""
		h = self.rand
		d = _sus(h, self.fonturi[font])
		return MultiContentEntryText(pos=(x, d), size=(w, h - d), font=font, flags=RT_HALIGN_LEFT | RT_VALIGN_TOP,
			text=text, color=culoare, color_sel=culoare)

	def _intrare(self, r):
		c, w = self.c, self.latime
		le = int(w * 0.30)
		# primul element e cheia randului: un rand cu None nu se poate alege, iar lista fara randuri de ales nu se
		# deruleaza cu pageUp/pageDown (banda aleasa are culoarea fundalului, deci nu se vede)
		if r[0] == "titlu":
			return [r[0], self._text(0, w, 0, r[1], c["titlu"])]
		# valorile raman intregi: un rand care nu incape deruleaza (lib/gui/elabel.h)
		if r[0] == "linie":
			# un element al listei de deasupra (o extensie oprita), in coloana valorilor
			return [r[0], self._text(le, w - le, 1, r[1] or "", c[M.NORMAL])]
		if r[0] == "nota":
			return [r[0], self._text(le, w - le, 2, r[1] or "", c["eticheta"])]
		_fel, eticheta, valoare, ton = r
		culoare = c.get(ton, c[M.NORMAL])
		return [r[0],
			self._text(self.x(20), le - self.x(28), 1, eticheta, c["eticheta"]),
			self._text(le, w - le, 1, valoare or "", culoare),
		]

	def _nota(self):
		if self.brutVizibil:
			text = _("Stânga/Dreapta: alt fișier · Sus/Jos: derulare · OK: pe scurt · EXIT: înapoi")
		else:
			text = _("Sus/Jos: derulare · OK sau ALBASTRU: textul brut · EXIT: înapoi")
		self["nota"].setText(text)

	def _arataBrut(self):
		if not self.pagini:
			self.setTitle(self.titluEcran)
			self["titlu"].setText(self.titluEcran)
			self["brut"].setText(_("Nu există niciun fișier de arătat."))
			return
		self.pagina %= len(self.pagini)
		titlu, cale, text = self.pagini[self.pagina]
		t = M.titluPagina(titlu, self.pagina + 1, len(self.pagini))
		self.setTitle(t)
		self["titlu"].setText(t)
		self["brut"].setText((_("Fișierul: %s") % cale) + "\n\n" + text)

	def keyAlbastru(self):
		if self.citeste:
			return
		self.brutVizibil = not self.brutVizibil
		if self.brutVizibil:
			self.pagina = 0
			self.pagini = []
			self["lista"].hide()
			self["brut"].show()
			self["brut"].setText(_("Se citesc fișierele..."))
			self["key_blue"].setText(_("Pe scurt"))
			# rapoartele si jurnalul au zeci de KiB: citite pe un fir, puse pe ecran din firul enigma2
			self.citeste = True
			M.peFir(M.paginiBrute, self._paginiGata)
		else:
			self["brut"].hide()
			self["lista"].show()
			self["key_blue"].setText(_("Text brut"))
			self.setTitle(self.titluEcran)
			self["titlu"].setText(self.titluEcran)
		self._nota()

	def _paginiGata(self, pagini, eroare):
		self.citeste = False
		if self.inchis:
			return
		if eroare is not None:
			print("[HdsModSigur] textul brut: %s" % eroare)
		self.pagini = pagini or []
		if self.brutVizibil:
			self._arataBrut()

	def _nimic(self):
		pass

	def keySus(self):
		if self.brutVizibil:
			self["brut"].pageUp()
		else:
			self["lista"].pageUp()

	def keyJos(self):
		if self.brutVizibil:
			self["brut"].pageDown()
		else:
			self["lista"].pageDown()

	def keyStanga(self):
		if self.brutVizibil and self.pagini:
			self.pagina -= 1
			self._arataBrut()

	def keyDreapta(self):
		if self.brutVizibil and self.pagini:
			self.pagina += 1
			self._arataBrut()
