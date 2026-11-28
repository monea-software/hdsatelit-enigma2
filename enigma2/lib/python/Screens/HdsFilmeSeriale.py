# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""„Filme și seriale”: filmele si serialele din televiziunea prin internet, asezate ca intr-o biblioteca media de acasa.

Acasa: fundalul mare al titlului ales in spate, sus titlul, anul, durata, nota si descrierea, dedesubt randuri orizontale de
postere („Continuă să vizionezi”, „Favorite”, „Adăugate recent”, categoriile furnizorului, cele in limba receptorului primele).
Pagina filmului: poster, fundal, descriere, regia, actorii, pistele cunoscute, butoanele Continuă / De la început / Favorite.
Pagina serialului: sezoanele ca file, episoadele pe un rand cu imaginea lor si bara de progres.
Desenul: design-web-stitch/skin-pro/vod (vod-acasa, vod-film, vod-serial), culorile temei HD Satelit.
Datele vin numai din Components/HdsVod.py (stratul de sursa), posterele din HdsVodPoze, pozitiile din HdsVodPozitii.
Navigarea: sagetile si OK; nimic de pus sau de confirmat.
"""
from enigma import eListboxPythonMultiContent, eServiceReference, eTimer, eLabel, eSize, fontRenderClass, RT_HALIGN_LEFT, RT_HALIGN_CENTER, \
	RT_VALIGN_CENTER, RT_VALIGN_TOP, RT_WRAP

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryProgress, \
	MultiContentEntryRectangle, MultiContentEntryText
from Components.Pixmap import Pixmap
from Screens.InfoBar import MoviePlayer
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

from Components import HdsVod as V
from Components import HdsVodPoze as P
from Components import HdsVodPozitii as Z
from Components import HdsMarireText as MT
import time


def N_(text):
	return text


T_CONTINUA = N_("Continuă să vizionezi")
T_FAVORITE = N_("Favorite")
T_RECENTE = N_("Adăugate recent")
T_REZULTATE = N_("Rezultate pentru „%s”")
T_FILME = N_("Filme")
T_SERIALE = N_("Seriale")
T_CAUTA = N_("Caută")
T_INCARCA = N_("Se încarcă...")
T_GOL = N_("Nimic aici încă.")
T_FARA_SERVER = N_("Nu ai încă un server %s. Apasă OK: îl caut în rețea, apoi scrii utilizatorul și parola.")
T_CAUT_SERVER = N_("Caut serverul %s în rețea...")
T_SCRIU_ADRESA = N_("Scriu adresa de mână")
T_ADRESA = N_("Adresa serverului %s (de exemplu 192.168.1.10:8096)")
T_UTILIZATOR = N_("Utilizatorul de pe serverul %s")
T_PAROLA = N_("Parola utilizatorului (poate fi goală)")
T_MA_LEG = N_("Mă conectez la server...")
T_LEGAT = N_("Gata: serverul %s este adăugat.")
T_ADAUGA_SERVER = N_("Adaugă un server %s")
T_SCOATE_SERVER = N_("Scoate serverul %s")
T_SCHIMBA_SERVER = N_("Schimbă utilizatorul sau parola")
T_CAUTA_DIN_NOU = N_("Caută din nou pe discuri")
T_SURSA = N_("Sursa")

C_FOND = 0x0B1020
C_PANOU = 0x1A2340
C_ALES = 0x374EA1
C_TEXT = 0xF2F4F8
C_TEXT2 = 0xC9D2E3
C_ETICHETA = 0xAEB9CC
C_VERDE = 0x4FD18B
FEREASTRA = 14                  # cate postere se tin incarcate de o parte si de alta a celui ales


def _inaltimeRand(lista, baza):
	"""Rand orizontal: textul creste numai in caseta disponibila din skin."""
	h = MT.inaltimeCod(baza)
	if MT.marit():
		h = min(h, lista.instance.size().height())
	return h


def textNota(nota):
	return (_("Nota %s") % nota.replace(".", ",")) if nota else ""


def textOra(secunde):
	s = int(secunde)
	return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60) if s >= 3600 else "%d:%02d" % (s // 60, s % 60)


def textCale():
	"""Firul de sus al celor trei ecrane, in limba receptorului (FSV, 15.11.2026: ca text fix in skin ramanea „Filme și seriale” in
	romana si pe un receptor in franceza sau engleza; numele ecranului e deja tradus)."""
	return "HD SATELIT  ›  " + _("Filme și seriale")


def randMeta(d):
	parti = [d.get("an") or "", V.textDurata(d.get("durata") or 0), textNota(d.get("nota") or ""), d.get("gen") or "",
		d.get("varsta") or ""]
	return "  ·  ".join(p for p in parti if p)


class _Rand(object):
	"""Un rand de postere de pe ecranul de acasa."""

	def __init__(self, fel, titlu, cat="", titluri=None):
		self.fel, self.titlu, self.cat = fel, titlu, cat
		self.titluri = titluri
		self.lucrare = ""
		self.i = 0
		self.mesaj = ""


class _Postere(object):
	"""Desenul unui rand orizontal (MenuList cu listOrientation="horizontal"): posterul, chenarul albastru pe cel ales,
	titlul sub el si, la „Continuă”, bara de progres. Pozele se incarca numai in fereastra din jurul celui ales."""

	_masuri = {}                     # (font, marime, text, latime, inaltime, rand unic) -> (latime, inaltime), pentru toate randurile
	_pixmapi = {}                    # cale -> pixmap, in ordinea folosirii: posterele randurilor vazute, refolosite la redesenare
	MAX_MASURI = 4000
	MAX_PIXMAPI = 64                 # 2 randuri x 29 de postere in fereastra, plus cateva

	@classmethod
	def uita(cls):
		"""Ecranul s-a inchis: masuratorile si pozele tinute minte nu mai ocupa memorie."""
		cls._masuri.clear()
		cls._pixmapi.clear()

	def _masura(self, f, font, text, w, h, flags):
		"""eLabel.calculateTextSize, tinut minte: acelasi titlu se masura din nou la fiecare desen al randului."""
		cheie = (font, f.pointSize, text, w, h, not bool(flags & RT_WRAP))
		m = self._masuri.get(cheie)
		if m is None:
			if len(self._masuri) >= self.MAX_MASURI:
				self._masuri.clear()
			r = eLabel.calculateTextSize(f, text, eSize(w, h), cheie[5])
			m = self._masuri[cheie] = (r.width(), r.height())
		return m

	def _pixmap(self, cale):
		"""LoadPixmap, tinut minte pentru posterele randurilor vazute: un rand redesenat nu mai decodeaza iar 29 de JPEG-uri."""
		px = self._pixmapi.pop(cale, None)
		if px is None:
			px = LoadPixmap(cale)
			if not px:
				lipsa = getattr(P, "lipsa", None)
				if lipsa:
					lipsa(cale)
				return px
		self._pixmapi[cale] = px
		while len(self._pixmapi) > self.MAX_PIXMAPI:
			del self._pixmapi[next(iter(self._pixmapi))]
		return px

	def __init__(self, lista, latime, inaltime, scara, cu_titlu=True, lat=False):
		self.lista, self.scara = lista, scara
		self.lat = lat
		self.l, self._inaltime = latime, inaltime
		self.cu_titlu = cu_titlu
		self.date = []
		self.incarcate = set()
		self.cuPoza = set()             # id-urile titlurilor din fereastra desenate cu poster
		self.progres = lambda t: 0.0
		self._pus = None                # (titluri, cate, latime, inaltime, progres) ale desenului de acum; None = de refacut
		l = lista.l
		self._fonturi = [MT.fontCod("Regular", int(22 * scara)), MT.fontCod("Bold", int(24 * scara))]
		for n, font in enumerate(self._fonturi):
			l.setFont(n, font)
		self._marimi()
		self._fond = MultiContentEntryRectangle(pos=(0, 0), size=(self.l, self.ph + 2 * int(4 * scara)), backgroundColor=C_FOND,
			backgroundColorSelected=C_ALES)

	def _marimi(self):
		"""Pastreaza proportia pozelor si loc pentru doua randuri de titlu marit."""
		s = self.scara
		veche = getattr(self, "h", None)
		self.h = _inaltimeRand(self.lista, self._inaltime)
		self.pl = int(self.l - 8 * s)
		raport = 9 / 16 if self.lat else 3 / 2
		if MT.marit():
			rezerva = int(4 * s) + MT.inaltimeCod(int(64 * s)) if self.cu_titlu else 0
			loc = self.h - 2 * int(4 * s) - rezerva
			self.pl = min(self.pl, max(1, int(loc / raport)))
		self.ph = int(self.pl * raport)
		self._pus = None
		if self.h != veche:
			self.lista.l.setItemHeight(self.h)

	def _text(self, pos, size, font, flags, text, **culori):
		"""Pastreaza desenul care incape; numai depasirea trece pe o linie derulabila."""
		if not text:
			return MultiContentEntryText(pos=pos, size=size, font=font, flags=flags, text=text, **culori)
		f = self._fonturi[font]
		x, y = pos
		w, h = size
		limita = min(self.h, self.lista.instance.size().height())
		latime, inaltime = self._masura(f, font, text, w, h, flags)
		# calculateTextSize masoara literele, fara spatiul de deasupra lor la valign top.
		nevoie = inaltime + (f.pointSize * 45 // 100 + 2 if flags & RT_VALIGN_TOP else 2)
		if text and (latime > w or nevoie > min(h, limita - y)):
			text = text.replace("\r", " ").replace("\n", " ")
			linie = fontRenderClass.getInstance().getLineHeight(f)
			h = max(int(linie + 1), (f.pointSize * 3 + 1) // 2) + max(2, int(4 * self.scara))
			# Nu micsoram posterul: daca titlul de jos iese din widget, il suprapunem pe baza lui.
			nou_y = max(0, min(y, limita - h))
			if nou_y != y:
				culori.update(backcolor=C_PANOU, backcolor_sel=C_PANOU)
			y = nou_y
			flags = (flags & ~(RT_WRAP | RT_VALIGN_TOP)) | RT_VALIGN_CENTER
		return MultiContentEntryText(pos=(x, y), size=(w, h), font=font, flags=flags, text=text, **culori)

	def _intrare(self, t, cu_poza, progres=0.0):
		s = self.scara
		x0, y0 = int(4 * s), int(4 * s)
		px0 = (self.l - self.pl) // 2 if MT.marit() else x0
		# 0.7.8 (CR3, Ozgur 18.11.2026): primul element e True, nu None. eListboxPythonMultiContent socoteste intrarea cu None
		# in cap "de neales", iar moveSelection (STANGA/DREAPTA intre episoadele serialului, HdsSerialPagina._muta) se
		# intorcea pe loc; randurile ecranului principal mutau cu moveToIndex, de aceea acolo mergea.
		e = [True,
			MultiContentEntryRectangle(pos=(0, 0), size=(self.l, self.ph + 2 * y0), backgroundColor=C_FOND,
				backgroundColorSelected=C_ALES),
			self._text(pos=(px0, y0), size=(self.pl, self.ph), font=1, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER | RT_WRAP,
				text=t.get("nume", ""), color=C_TEXT2, color_sel=C_TEXT, backcolor=C_PANOU, backcolor_sel=C_PANOU)]
		px = None
		if cu_poza and t.get("poza"):
			p = P.cere(t["poza"], self.pl, self.ph, "lat" if self.lat else "poster")
			if p:
				px = self._pixmap(p)
				if px:
					e.append(MultiContentEntryPixmapAlphaBlend(pos=(px0, y0), size=(self.pl, self.ph), png=px))
		if self.lat and t.get("sub"):
			# placa lata (desenul Stitch): titlul pe placa, jos; sub placa ramane „mai sunt ...”
			h = MT.inaltimeCod(int(40 * s))
			y = y0 + self.ph - (int(14 * s) + h if MT.marit() else int(54 * s))
			e.append(self._text(pos=(px0 + int(12 * s), y), size=(self.pl - int(24 * s), h),
				font=1, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=t.get("nume", ""), color=C_TEXT, color_sel=C_TEXT))
		if progres > 0:
			e.append(MultiContentEntryProgress(pos=(px0, y0 + self.ph - int(8 * s)), size=(self.pl, int(8 * s)),
				percent=int(progres * 100), borderWidth=0, foreColor=C_VERDE if progres >= 1 else C_ALES,
				foreColorSelected=C_VERDE if progres >= 1 else C_ALES, backColor=0x000000, backColorSelected=0x000000))
		if self.cu_titlu:
			sub = t.get("sub") or ""
			# cu marginea posterului de o parte si de alta: titlurile vecine nu se mai lipesc intr-un singur sir (FSV, 15.11.2026);
			# cel ales, daca nu incape, deruleaza (lista orizontala)
			e.append(self._text(pos=(x0, self.ph + 2 * y0 + int(4 * s)), size=(self.l - 2 * x0, self.h - self.ph - 2 * y0 - int(4 * s)),
				font=0, flags=RT_HALIGN_CENTER | RT_VALIGN_TOP | RT_WRAP, text=sub or t.get("nume", ""), color=C_TEXT2, color_sel=C_TEXT))
		if px:
			del e[2]
			self.cuPoza.add(id(t))
		return e

	def _gol(self):
		"""Intrarea din afara ferestrei: numai fondul, fara text si fara poza (nu se vede; fereastra trece de marginile randului
		vazut). Un rand de 3.000 de titluri nu mai cere 6.000 de masuratori de text la fiecare tasta."""
		return [True, self._fond]

	def pune(self, titluri, i, progres=None):
		semn = (titluri, len(titluri or ()), self.l, self.ph, progres)
		if titluri and self._pus is not None and titluri is self._pus[0] and semn[1:] == self._pus[1:]:
			# acelasi rand, deja desenat (o alta lucrare s-a terminat): numai locul celui ales
			if self.lista.getSelectionIndex() != i:
				self.lista.moveToIndex(min(i, len(self.date) - 1))
				self.fereastra(i)
			return
		self._pus = semn
		self.date = titluri or []
		self.progres = progres or (lambda t: 0.0)
		self.cuPoza = set()
		self._fond = MultiContentEntryRectangle(pos=(0, 0), size=(self.l, self.ph + 2 * int(4 * self.scara)), backgroundColor=C_FOND,
			backgroundColorSelected=C_ALES)
		self.incarcate = set(range(max(0, i - FEREASTRA), min(len(self.date), i + FEREASTRA + 1)))
		intrari = [None] * len(self.date)
		# cele mai departe de cel ales intai: pozele cerute ultimele se aduc primele (HdsVodPoze, coada cu cea mai noua intai)
		for n in sorted(self.incarcate, key=lambda n: -abs(n - i)):
			intrari[n] = self._intrare(self.date[n], True, self.progres(self.date[n]))
		self.lista.setList([e if e is not None else self._gol() for e in intrari])
		if self.date:
			self.lista.moveToIndex(min(i, len(self.date) - 1))

	def fereastra(self, i, toate=False):
		"""Muta fereastra in jurul lui i: cele care intra se fac intregi, cele care ies raman numai cu fondul. toate=True (au venit
		poze noi): se refac numai intrarile din fereastra care inca n-au posterul si al caror poster e acum gata."""
		noi = set(range(max(0, i - FEREASTRA), min(len(self.date), i + FEREASTRA + 1)))
		de_facut = noi - self.incarcate
		if toate:
			# P.cere si pentru cele care inca nu sunt gata: o cerere iesita din coada (plina) se pune iar, cea de langa cel ales ultima
			fel = "lat" if self.lat else "poster"
			for n in sorted(noi & self.incarcate, key=lambda n: -abs(n - i)):
				t = self.date[n]
				if t.get("poza") and id(t) not in self.cuPoza and P.cere(t["poza"], self.pl, self.ph, fel):
					de_facut.add(n)
		for n in self.incarcate - noi:
			if 0 <= n < len(self.date):
				self.cuPoza.discard(id(self.date[n]))
				self.lista.list[n] = self._gol()
				self.lista.l.invalidateEntry(n)
		for n in sorted(de_facut, key=lambda n: -abs(n - i)):
			if 0 <= n < len(self.date):
				self.lista.list[n] = self._intrare(self.date[n], True, self.progres(self.date[n]))
				self.lista.l.invalidateEntry(n)
		self.incarcate = noi


class HdsFilmeSeriale(Screen):
	skin = """
	<screen name="HdsFilmeSeriale" position="0,0" size="1920,1080" resolution="1920,1080" flags="wfNoBorder" backgroundColor="#000b1020" title="Filme și seriale">
		<widget name="fundal" position="0,0" size="1920,1080" scale="1" zPosition="0" />
		<widget name="cale" position="96,40" size="520,50" font="Bold;32" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="surse" position="624,38" size="940,54" zPosition="2" listOrientation="horizontal" itemWidth="235" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="sursa" position="96,92" size="1500,28" font="Regular;22" noWrap="1" foregroundColor="#00aeb9cc" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget source="global.CurrentTime" render="Label" position="1580,36" size="244,58" font="Bold;40" halign="right" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" zPosition="2">
			<convert type="ClockToText">Default</convert>
		</widget>
		<widget name="titlu" position="96,120" size="1500,72" font="Bold;56" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="meta" position="96,196" size="1500,40" font="Regular;28" noWrap="1" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="descriere" position="96,240" size="1180,76" font="Regular;26" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="file" position="96,326" size="880,56" zPosition="2" listOrientation="horizontal" itemWidth="220" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="stare" position="1000,334" size="824,40" font="Regular;24" halign="right" foregroundColor="#00f1c40f" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="3" />
		<widget name="eticheta0" position="96,396" size="1500,38" font="Bold;28" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="rand0" position="88,438" size="1744,300" zPosition="2" listOrientation="horizontal" itemWidth="170" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="eticheta1" position="96,744" size="1500,38" font="Bold;28" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="rand1" position="88,786" size="1744,244" zPosition="2" listOrientation="horizontal" itemWidth="170" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="legenda" position="96,1034" size="1728,38" font="Regular;24" foregroundColor="#00aeb9cc" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="3" />	</screen>
	"""

	def __init__(self, session, sursa_id=None, tip=V.FILME):
		Screen.__init__(self, session)
		self._inceput = time.monotonic()
		self._masurat = set()
		self.setTitle(_("Filme și seriale"))
		self.surse = V.surse()
		self.src = next((s for s in self.surse if s.id == sursa_id), self.surse[0] if self.surse else None)
		self.grupa = self.src.grupa if self.src else V.GRUPE[0][0]
		self._server = None          # adaugarea unui server: {"fel", "faza", "fir", "rez", ...}
		self.tip = tip
		self.randuri = []
		self.ales = 0                # randul ales; -1 = filele de sus
		self.sus = 0                 # primul rand vazut
		self._gen = -1
		self._detalii = {}           # (tip, id) -> detalii (numai ultimele cateva)
		self._lucrareDetalii = ""
		self._deDetaliat = None
		self._recente = ""           # lucrarea „Adăugate recent” (din fisier, apoi, daca lipseste, lista intreaga)
		self._miscat = False         # omul a mers prin randuri (sus, jos, stanga, dreapta) de la deschiderea filei
		self["fundal"] = Pixmap()
		self["file"] = MenuList([], content=eListboxPythonMultiContent)
		self["surse"] = MenuList([], content=eListboxPythonMultiContent)
		for n in ("sursa", "titlu", "meta", "descriere", "eticheta0", "eticheta1", "stare", "legenda"):
			self[n] = Label("")
		self["cale"] = Label(textCale())
		self["rand0"] = MenuList([], content=eListboxPythonMultiContent)
		self["rand1"] = MenuList([], content=eListboxPythonMultiContent)
		self["legenda"].setText(_("OK Deschide   ·   Verde Redă   ·   Galben Caută   ·   Albastru Favorite   ·   MENU Sursa   ·   EXIT Ieșire"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], {
			"ok": self._ok, "cancel": self._iesi, "red": self._iesi, "green": self._reda, "yellow": self._cauta,
			"blue": self._favorit, "left": self._stanga, "right": self._dreapta, "up": self._sus, "down": self._jos,
			"menu": self._alegeSursa,
		}, -2)
		self._ceas = eTimer()
		self._ceas.callback.append(self._pas)
		self._ceasDetalii = eTimer()
		self._ceasDetalii.callback.append(self._cereDetalii)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._inchide)

	# ------------------------------------------------------------ pregatirea

	def _pregateste(self):
		w = self["rand0"].instance.size().width()
		self.scara = w / 1744.0
		for n in ("rand0", "rand1"):
			self[n].instance.setSelectionEnable(False)
		self.desen = [_Postere(self["rand0"], int(170 * self.scara), int(300 * self.scara), self.scara),
			_Postere(self["rand1"], int(170 * self.scara), int(300 * self.scara), self.scara)]
		self._formaRand = [None, None]
		f = self["file"].l
		f.setFont(0, MT.fontCod("Bold", int(28 * self.scara)))
		self._hFile = _inaltimeRand(self["file"], int(52 * self.scara))
		f.setItemHeight(self._hFile)
		g = self["surse"].l
		g.setFont(0, MT.fontCod("Bold", int(24 * self.scara)))
		self._hSurse = _inaltimeRand(self["surse"], int(50 * self.scara))
		g.setItemHeight(self._hSurse)
		self._surseRand()
		self._file()
		if self.src is None:
			self.ales = -2
			self._ceas.start(300, False)
			self._grupaGoala()
			self._arata()
			return
		self._pornesteTip()
		self._masura("ecranul desenat")
		self._ceas.start(300, False)

	def _file(self):
		s = self.scara
		lat = int(220 * s)
		intrari = []
		for t in (T_FILME, T_SERIALE, T_CAUTA):
			intrari.append([t, MultiContentEntryText(pos=(0, 0), size=(lat - int(12 * s), self._hFile), font=0,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=_(t), color=C_ETICHETA, color_sel=C_TEXT, backcolor=C_FOND,
				backcolor_sel=C_ALES)])
		self["file"].setList(intrari)
		self["file"].moveToIndex(0 if self.tip == V.FILME else 1)
		self["file"].instance.setSelectionEnable(self.ales == -1)
		din_grupa = V.surseGrupa(self.grupa, self.surse)
		self["sursa"].setText(self.src.nume if self.src and len(din_grupa) > 1 else "")

	def _surseRand(self):
		"""Randul de sus: Furnizor IPTV / Pe disc / Emby / Jellyfin (SUS din file il alege, STANGA/DREAPTA schimba sursa)."""
		s = self.scara
		lat = int(235 * s)
		intrari = []
		for grupa, text in V.GRUPE:
			intrari.append([grupa, MultiContentEntryText(pos=(0, 0), size=(lat - int(10 * s), self._hSurse), font=0,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=_(text), color=C_ETICHETA, color_sel=C_TEXT, backcolor=C_FOND,
				backcolor_sel=C_ALES)])
		self["surse"].setList(intrari)
		self["surse"].moveToIndex(next((i for i, g in enumerate(V.GRUPE) if g[0] == self.grupa), 0))
		self["surse"].instance.setSelectionEnable(self.ales == -2)

	def _schimbaGrupa(self):
		i = self["surse"].getSelectionIndex()
		grupa = V.GRUPE[i][0] if 0 <= i < len(V.GRUPE) else self.grupa
		if grupa == self.grupa and self.src is not None:
			return
		self.grupa = grupa
		lista = V.surseGrupa(grupa, self.surse)
		for r in self.randuri:
			if r.lucrare:
				V.renunta(r.lucrare)
		self.src = lista[0] if lista else None
		self._detalii = {}
		self["stare"].setText("")
		self._file()
		if self.src is None:
			self._grupaGoala()
		else:
			self._pornesteTip()
		self.ales, self.sus = -2, 0
		self._arata()

	def _grupaGoala(self):
		"""O sursa fara cont sau server: ce are omul de facut, scris pe ecran (la Emby/Jellyfin, OK incepe adaugarea)."""
		if self._recente:
			V.renunta(self._recente)
		self._recente = ""
		self.randuri = []
		self._categorii = _Rand("categorii", "")
		nume = dict(V.GRUPE).get(self.grupa, "")
		self["titlu"].setText(_(nume))
		self["meta"].setText("")
		if self.grupa in ("emby", "jellyfin"):
			self["descriere"].setText(_(T_FARA_SERVER) % _(nume))
		else:
			self["descriere"].setText(_(V.E_FARA_SURSA))
		self["fundal"].hide()

	def _pornesteTip(self):
		"""Randurile de pe ecran pentru filme sau seriale: cele locale (fara retea) imediat, apoi recente si categoriile.
		„Adăugate recent” vine din fisier, pe loc; randul apare numai cand are titluri (cand fisierul lipseste, dupa lista intreaga,
		in fundal), fara „Se încarcă...” cat se citeste lista."""
		for r in self.randuri:
			if r.lucrare:
				V.renunta(r.lucrare)
		if self._recente:
			V.renunta(self._recente)
		self._recente = ""
		self.randuri = []
		sid = self.src.id
		cont = [self._dinPozitii(k, r) for k, r in Z.continua(sid) if (r.get("tip") or V.FILME) == self.tip]
		if cont and not self.src.continuaPeServer:
			self.randuri.append(_Rand("continua", _(T_CONTINUA), titluri=cont))
		fav = [self._dinPozitii(k, r) for k, r in Z.favorite(sid) if (r.get("tip") or V.FILME) == self.tip]
		if fav:
			self.randuri.append(_Rand("favorite", _(T_FAVORITE), titluri=fav))
		if V.activ("recente") and not getattr(self.src, "fara_recente", False):   # 0.7.7 (FLM2): un playlist nu are date
			self._recente = V.cere("recente", sid, self.tip)
		self._categorii = _Rand("categorii", "")
		self._categorii.lucrare = V.cere("categorii", sid, self.tip)
		self.ales, self.sus = 0, 0
		self._miscat = False
		self._arata()

	def _dinPozitii(self, k, r):
		"""Un titlu din fisierul pozitiilor sau al favoritelor (fara retea)."""
		cheie = k.split("/", 1)[1] if "/" in k else k
		t = {"nume": r.get("nume") or cheie, "poza": r.get("fundal") or r.get("poza") or "", "k": k}
		if cheie.startswith("s"):
			t.update(id=cheie[1:], tip=V.SERIALE)
		elif r.get("serial"):
			# un episod inceput: se deschide serialul, cu episodul ales
			t.update(id=r["serial"], tip=V.SERIALE, episod=cheie, nume=r.get("serial_nume") or t["nume"],
				sub=(_("S%s E%s") % (r.get("sezon", "?"), r.get("numar", "?"))) + "  " + _("mai sunt %s") % V.textDurata(max(0, r.get("d", 0) - r.get("p", 0))))
		else:
			t.update(id=cheie[1:].split(".")[0], tip=V.FILME, cheie=cheie)
			if r.get("d"):
				t["sub"] = _("mai sunt %s") % V.textDurata(max(0, r.get("d", 0) - r.get("p", 0)))
		return t

	# ------------------------------------------------------------ ceasul: lucrarile terminate, pozele noi

	def _masura(self, ce):
		"""Timpii deschiderii, o data pe fiecare pas, in jurnalul interfetei (proba ceruta: cat dureaza deschiderea ecranului)."""
		if ce not in self._masurat:
			self._masurat.add(ce)
			print("[HdsFilmeSeriale] %s dupa %d ms" % (ce, (time.monotonic() - self._inceput) * 1000))

	def _pas(self):
		if self._server and self._server.get("gata"):
			self._serverPas()
		if self.src is None:
			return
		schimbat = False
		if self._categorii.lucrare:
			rez = V.rezultat(self._categorii.lucrare)
			if not rez.get("lucreaza"):
				self._categorii.lucrare = ""
				self._masura("categoriile")
				if rez.get("result"):
					for c in rez.get("categorii", []):
						self.randuri.append(_Rand("categorie", c["nume"], cat=c["id"]))
					if not rez.get("categorii") and self.src.grupa == "disc":
						from Components import HdsVodDisc
						self["stare"].setText(_(HdsVodDisc.E_GOL))
				else:
					self["stare"].setText(_(rez.get("message") or V.E_NU_RASPUNDE))
				schimbat = True
		if self._recente:
			rez = V.rezultat(self._recente)
			if not rez.get("lucreaza"):
				self._recente = ""
				if rez.get("result") and rez.get("titluri"):
					self._masura("randul recente")
					self._puneRecente(rez["titluri"])
					schimbat = True
				elif rez.get("aduce"):
					self._recente = rez["aduce"]      # fisierul lipseste: lista intreaga se citeste in fundal
		for r in self.randuri:
			if r.lucrare:
				rez = V.rezultat(r.lucrare)
				if rez.get("lucreaza"):
					if r.fel == "cautare" and rez.get("titluri") and len(rez["titluri"]) != len(r.titluri or []):
						r.titluri = rez["titluri"]
						schimbat = True
					continue
				r.lucrare = ""
				self._masura("randul " + r.fel)
				r.titluri = rez.get("titluri") or [] if rez.get("result") else []
				r.mesaj = "" if rez.get("result") else _(rez.get("message") or V.E_NU_RASPUNDE)
				schimbat = True
		if self._lucrareDetalii:
			rez = V.rezultat(self._lucrareDetalii)
			if not rez.get("lucreaza"):
				self._lucrareDetalii = ""
				if rez.get("result"):
					d = rez["detalii"]
					self._detalii[(d["tip"], d["id"])] = d
					if len(self._detalii) > 30:
						self._detalii.pop(next(iter(self._detalii)))
					self._info()
		if schimbat:
			self._arata()
		elif P.generatie() != self._gen:
			self._gen = P.generatie()
			for n, d in enumerate(self.desen):
				r = self._randVazut(n)
				if r is not None and r.titluri:
					d.fereastra(r.i, toate=True)
			self._fundal()

	def _puneRecente(self, titluri):
		"""Randul „Adăugate recent” la locul lui (dupa rezultatele cautarii, Continuă si Favorite). Cat omul n-a mers prin randuri,
		alesul ramane pe acelasi loc, deci randul nou se vede si e ales; dupa ce a mers, randul ales ramane acelasi pe ecran."""
		i = sum(1 for r in self.randuri if r.fel in ("cautare", "continua", "favorite"))
		self.randuri.insert(i, _Rand("recente", _(T_RECENTE), titluri=titluri))
		if self._miscat and self.ales >= i:
			self.ales += 1
			self.sus = max(0, self.ales)

	# ------------------------------------------------------------ desenul

	def _randVazut(self, n):
		i = self.sus + n
		return self.randuri[i] if 0 <= i < len(self.randuri) else None

	def _cereRand(self, r):
		if r.titluri is None and not r.lucrare and r.fel in ("recente", "categorie"):
			r.lucrare = V.cere("recente" if r.fel == "recente" else "rand", self.src.id, self.tip, r.cat)

	def _progres(self, t):
		k = t.get("k") or (Z.cheie(self.src.id, t["cheie"]) if t.get("cheie") else "")
		return Z.progres(k) if k else 0.0

	def _arata(self):
		for n in range(2):
			r = self._randVazut(n)
			if r is not None:
				self._cereRand(r)
		r2 = self._randVazut(2)
		if r2 is not None:
			self._cereRand(r2)
		for n, d in enumerate(self.desen):
			r = self._randVazut(n)
			self["eticheta%d" % n].setText(r.titlu if r else "")
			self._forma(n, d, r is not None and r.fel == "continua")
			if r is None:
				d.pune([], 0)
			elif r.titluri is None:
				d.pune([{"nume": _(T_INCARCA)}], 0)
			elif not r.titluri:
				d.pune([{"nume": r.mesaj or _(T_GOL)}], 0)
			else:
				d.pune(r.titluri, r.i, self._progres if r.fel in ("continua", "favorite", "recente", "categorie", "cautare") else None)
			self["rand%d" % n].instance.setSelectionEnable(self.ales >= 0 and self.sus + n == self.ales)
		self["file"].instance.setSelectionEnable(self.ales == -1)
		self["surse"].instance.setSelectionEnable(self.ales == -2)
		if self.src is not None:
			self._info()

	def _forma(self, n, d, lat):
		"""Placi late la „Continuă să vizionezi”, postere inalte in rest: latimea elementului se schimba pe loc."""
		if self._formaRand[n] == lat:
			return
		self._formaRand[n] = lat
		s = self.scara
		d.lat = lat
		d.l = int((300 if lat else 170) * s)
		d._marimi()
		self["rand%d" % n].instance.setItemWidth(d.l)

	def _titluAles(self):
		if self.ales < 0 or self.ales >= len(self.randuri):
			return None
		r = self.randuri[self.ales]
		if not r.titluri or not (0 <= r.i < len(r.titluri)) or "id" not in r.titluri[r.i]:
			return None
		t = r.titluri[r.i]
		t.setdefault("tip", self.tip)
		return t

	def _info(self):
		t = self._titluAles()
		if t is None:
			self["titlu"].setText(_("Filme") if self.tip == V.FILME else _("Seriale"))
			self["meta"].setText("")
			self["descriere"].setText("")
			return
		d = self._detalii.get((t["tip"], t["id"]))
		self["titlu"].setText((d or {}).get("nume") or t["nume"])
		self["meta"].setText(randMeta(d) if d else "  ·  ".join(x for x in (t.get("an", ""), textNota(t.get("nota", ""))) if x))
		self["descriere"].setText((d or {}).get("descriere") or "")
		if d is None:
			self._deDetaliat = t
			self._ceasDetalii.start(500, True)       # numai dupa ce omul se opreste pe titlu
		self._fundal()

	def _cereDetalii(self):
		t = self._deDetaliat
		if t is not None and t is self._titluAles():
			if self._lucrareDetalii:
				V.renunta(self._lucrareDetalii)
			self._lucrareDetalii = V.cere("detalii", self.src.id, t["tip"], t["id"])

	def _fundal(self):
		t = self._titluAles()
		d = self._detalii.get((t["tip"], t["id"])) if t else None
		adresa = (d or {}).get("fundal") or (d or {}).get("poster") or ""
		cale = P.cere(adresa, 960, 540, "fundal") if adresa else ""
		if cale != getattr(self, "_caleFundal", None):
			self._caleFundal = cale
			px = LoadPixmap(cale) if cale else None
			if px:
				self["fundal"].instance.setPixmap(px)
				self["fundal"].show()
			else:
				if cale:
					P.lipsa(cale)
					self._caleFundal = None
				self["fundal"].hide()

	# ------------------------------------------------------------ tastele

	def _stanga(self):
		if self.ales == -2:
			self["surse"].instance.moveSelection(self["surse"].instance.moveLeft)
			self._schimbaGrupa()
			return
		if self.ales < 0:
			self["file"].instance.moveSelection(self["file"].instance.moveLeft)
			self._schimbaFila()
			return
		self._muta(-1)

	def _dreapta(self):
		if self.ales == -2:
			self["surse"].instance.moveSelection(self["surse"].instance.moveRight)
			self._schimbaGrupa()
			return
		if self.ales < 0:
			self["file"].instance.moveSelection(self["file"].instance.moveRight)
			self._schimbaFila()
			return
		self._muta(1)

	def _muta(self, pas):
		r = self.randuri[self.ales] if 0 <= self.ales < len(self.randuri) else None
		if not r or not r.titluri:
			return
		self._miscat = True
		r.i = max(0, min(len(r.titluri) - 1, r.i + pas))
		n = self.ales - self.sus
		self["rand%d" % n].moveToIndex(r.i)
		self.desen[n].fereastra(r.i)
		self._info()

	def _schimbaFila(self):
		i = self["file"].getSelectionIndex()
		tip = V.FILME if i == 0 else (V.SERIALE if i == 1 else None)
		if tip and tip != self.tip:
			self.tip = tip
			self._pornesteTip()
			self.ales = -1
			self._arata()

	def _sus(self):
		if self.ales < 0:
			if self.ales == -1:
				self.ales = -2
				self._arata()
			return
		self.ales -= 1
		self.sus = max(0, self.ales)
		self._miscat = True
		self._arata()

	def _jos(self):
		if self.src is None:
			return
		if self.ales + 1 >= len(self.randuri):
			return
		self.ales += 1
		self.sus = max(0, self.ales)    # randul ales sta sus, ca in bibliotecile media; dedesubt se vede urmatorul
		self._miscat = True
		self._arata()

	def _ok(self):
		if self.ales == -2 or self.src is None:
			if self.src is None and self.grupa in ("emby", "jellyfin"):
				self._adaugaServer(self.grupa)
			elif self.src is not None:
				self.ales = 0 if self.randuri else -1
				self._arata()
			return
		if self.ales < 0:
			if self["file"].getSelectionIndex() == 2:
				self._cauta()
			else:
				self.ales = 0
				self._arata()
			return
		t = self._titluAles()
		if t is None:
			return
		if t["tip"] == V.SERIALE:
			self.session.openWithCallback(self._dupaPagina, HdsSerialPagina, self.src, t)
		else:
			self.session.openWithCallback(self._dupaPagina, HdsFilmPagina, self.src, t, self._detalii.get((V.FILME, t["id"])))

	def _dupaPagina(self, *a):
		# pozitiile si favoritele s-au putut schimba: randurile locale se refac, cele din retea raman (cu titlul ales)
		sid = self.src.id
		ales = self.randuri[self.ales] if 0 <= self.ales < len(self.randuri) else None
		locale = []
		cont = [self._dinPozitii(k, r) for k, r in Z.continua(sid) if (r.get("tip") or V.FILME) == self.tip]
		if cont and not self.src.continuaPeServer:
			locale.append(_Rand("continua", _(T_CONTINUA), titluri=cont))
		fav = [self._dinPozitii(k, r) for k, r in Z.favorite(sid) if (r.get("tip") or V.FILME) == self.tip]
		if fav:
			locale.append(_Rand("favorite", _(T_FAVORITE), titluri=fav))
		cautari = [r for r in self.randuri if r.fel == "cautare"]
		restul = [r for r in self.randuri if r.fel not in ("continua", "favorite", "cautare")]
		self.randuri = cautari + locale + restul
		if ales is not None and ales in self.randuri:
			self.ales = self.randuri.index(ales)
		elif ales is not None:
			gasit = [i for i, r in enumerate(self.randuri) if r.fel == ales.fel]
			self.ales = gasit[0] if gasit else 0
			if gasit:
				self.randuri[self.ales].i = min(ales.i, max(0, len(self.randuri[self.ales].titluri or []) - 1))
		self.ales = max(0 if self.ales >= 0 else self.ales, min(self.ales, len(self.randuri) - 1))
		self.sus = max(0, self.ales)
		for d in self.desen:
			d._pus = None               # progresul titlurilor s-a putut schimba si in randurile pastrate
		self._arata()

	def _reda(self):
		if self.src is None:
			return
		t = self._titluAles()
		if t is None:
			return
		if t["tip"] == V.SERIALE:
			self._ok()
			return
		cheie = t.get("cheie")
		if cheie:
			reda(self.session, self.src, cheie, {"nume": t["nume"], "poza": t.get("poza", ""), "tip": V.FILME},
				pozitieTitlu(self.src, Z.cheie(self.src.id, cheie)), self._dupaPagina)

	def _cauta(self):
		if self.src is None:
			return
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dupaCautare, VirtualKeyBoard, title=_("Caută filme și seriale"), text="")

	def _dupaCautare(self, text=None):
		text = (text or "").strip()[:80]
		if not text:
			return
		self.randuri = [r for r in self.randuri if r.fel != "cautare"]
		noi = []
		for tip in (V.FILME, V.SERIALE):
			r = _Rand("cautare", _(T_REZULTATE) % text + "  ·  " + (_("Filme") if tip == V.FILME else _("Seriale")), titluri=[])
			r.lucrare = V.cere("cauta", self.src.id, tip, text)
			noi.append(r)
		self.randuri = noi + self.randuri
		self.ales, self.sus = 0, 0
		self["stare"].setText(_("Caut în tot catalogul; rezultatele apar pe măsură ce le găsesc."))
		self._arata()

	def _favorit(self):
		if self.src is None:
			return
		t = self._titluAles()
		if t is None:
			return
		if t["tip"] == V.SERIALE:
			k = Z.cheie(self.src.id, "s" + t["id"])
		else:
			k = Z.cheie(self.src.id, t.get("cheie") or "")
		acum = Z.comutaFavorit(k, {"nume": t["nume"], "poza": t.get("poza", ""), "tip": t["tip"]})
		self["stare"].setText(_("Adăugat la favorite.") if acum else _("Scos de la favorite."))
		self._dupaPagina()

	def _alegeSursa(self):
		lista = [(s.nume, s) for s in V.surseGrupa(self.grupa, self.surse)] if len(V.surseGrupa(self.grupa, self.surse)) > 1 else []
		nume = _(dict(V.GRUPE).get(self.grupa, ""))
		if self.grupa in ("emby", "jellyfin"):
			lista.append((_(T_ADAUGA_SERVER) % nume, "adauga"))
			if self.src is not None:
				lista.append((_("Datele de acces: %s") % " / ".join(self.src.s.get(k, "") for k in ("utilizator", "parola", "jeton")), "date"))
				lista.append((_(T_SCHIMBA_SERVER), "schimba"))
				lista.append((_(T_SCOATE_SERVER) % self.src.nume, "scoate"))
		elif self.grupa == "disc" and self.src is not None:
			lista.append((_(T_CAUTA_DIN_NOU), "disc"))
		if not lista:
			return
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self._sursaAleasa, ChoiceBox, title=_(T_SURSA), list=lista)

	def _sursaAleasa(self, ales=None):
		if not ales:
			return
		if ales[1] == "adauga":
			self._adaugaServer(self.grupa)
		elif ales[1] == "date":
			from Screens.TextBox import TextBox
			self.session.open(TextBox, text="\n".join(self.src.s.get(k, "") for k in ("utilizator", "parola", "jeton")), title=_("Datele de acces"))
		elif ales[1] == "schimba":
			# aceeasi adresa, utilizatorul si parola scrise din nou (logarea noua inlocuieste serverul vechi daca merge)
			self._server = {"fel": self.grupa, "faza": "caut", "vechi": self.src.id, "utilizator": self.src.s.get("utilizator", ""), "parola": self.src.s.get("parola", "")}
			self._serverAdresa(self.src.adresa)
		elif ales[1] == "scoate":
			from Components import HdsVodServere
			HdsVodServere.scoate(self.src.id)
			self._reiaSursele()
		elif ales[1] == "disc":
			# indexul se reface pe firul de lucru, la cererea categoriilor (ecranul nu asteapta)
			self.src._index = None
			V.golesteMemoria()
			self._pornesteTip()
		elif ales[1] is not self.src:
			self.src = ales[1]
			self._file()
			self._pornesteTip()

	def _reiaSursele(self, sid=None):
		self.surse = V.surse()
		lista = V.surseGrupa(self.grupa, self.surse)
		self.src = next((x for x in lista if x.id == sid), lista[0] if lista else None)
		self._file()
		if self.src is None:
			self._grupaGoala()
		else:
			self._pornesteTip()
		self._arata()

	# ------------------------------------------------------------ adaugarea serverului Emby / Jellyfin

	def _inFundal(self, functie, *argumente):
		import threading
		self._server["gata"] = False

		def lucru():
			try:
				self._server["rez"] = functie(*argumente)
			except Exception as e:
				print("[HdsFilmeSeriale] server: %s" % type(e).__name__)
				self._server["rez"] = None
			self._server["gata"] = True
		fir = threading.Thread(target=lucru, name="HdsVodServer")
		fir.daemon = True
		fir.start()

	def _adaugaServer(self, fel):
		"""Regula 'cat mai simplu': serverul se cauta singur in retea (UDP 7359); omul scrie numai utilizatorul si parola."""
		from Components import HdsVodServere
		nume = HdsVodServere.NUME_FEL[fel]
		self._server = {"fel": fel, "faza": "caut"}
		self["stare"].setText(_(T_CAUT_SERVER) % nume)
		self._inFundal(HdsVodServere.descopera, 2.0, (fel,))

	def _serverPas(self):
		from Components import HdsVodServere
		from Screens.ChoiceBox import ChoiceBox
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		srv = self._server
		srv["gata"] = None
		nume = HdsVodServere.NUME_FEL[srv["fel"]]
		if srv["faza"] == "caut":
			self["stare"].setText("")
			gasite = srv.get("rez") or []
			if len(gasite) == 1:
				self._serverAles((gasite[0]["nume"], gasite[0]["adresa"]))
				return
			lista = [("%s  ·  %s" % (g["nume"], g["adresa"].split("://", 1)[-1]), g["adresa"]) for g in gasite]
			lista.append((_(T_SCRIU_ADRESA), ""))
			self.session.openWithCallback(self._serverAles, ChoiceBox, title=_(T_CAUT_SERVER) % nume, list=lista)
		elif srv["faza"] == "leg":
			ok, mesaj, sid = srv.get("rez") or (False, HdsVodServere.E_SERVER, "")
			self._server = None
			if ok:
				if srv.get("vechi") and srv["vechi"] != sid:
					HdsVodServere.scoate(srv["vechi"])          # alt utilizator pe acelasi server: cel vechi iese
				self["stare"].setText(_(T_LEGAT) % nume)
				self._reiaSursele(sid)
			else:
				self["stare"].setText(_(mesaj))

	def _serverAles(self, ales=None):
		from Components import HdsVodServere
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		if not ales or self._server is None:
			self._server = None
			return
		nume = HdsVodServere.NUME_FEL[self._server["fel"]]
		if not ales[1]:
			self.session.openWithCallback(self._serverAdresa, VirtualKeyBoard, title=_(T_ADRESA) % nume, text="")
			return
		self._serverAdresa(ales[1])

	def _serverAdresa(self, adresa=None):
		from Components import HdsVodServere
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		if not adresa or self._server is None:
			self._server = None
			return
		if not HdsVodServere.adresaBuna(adresa):
			self["stare"].setText(_(HdsVodServere.E_ADRESA))
			self._server = None
			return
		self._server["adresa"] = adresa
		nume = HdsVodServere.NUME_FEL[self._server["fel"]]
		self.session.openWithCallback(self._serverUtilizator, VirtualKeyBoard, title=_(T_UTILIZATOR) % nume, text=self._server.get("utilizator", ""))

	def _serverUtilizator(self, utilizator=None):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		if not utilizator or self._server is None:
			self._server = None
			return
		self._server["utilizator"] = utilizator.strip()
		self.session.openWithCallback(self._serverParola, VirtualKeyBoard, title=_(T_PAROLA), text=self._server.get("parola", ""))

	def _serverParola(self, parola=None):
		from Components import HdsVodServere
		if parola is None or self._server is None:
			self._server = None
			return
		srv = self._server
		srv["faza"] = "leg"
		self["stare"].setText(_(T_MA_LEG))
		self._inFundal(HdsVodServere.adauga, srv["fel"], srv["adresa"], srv["utilizator"], parola)

	def _iesi(self):
		if self.ales >= 0 and any(r.fel == "cautare" for r in self.randuri):
			for r in self.randuri:
				if r.fel == "cautare" and r.lucrare:
					V.renunta(r.lucrare)
			self.randuri = [r for r in self.randuri if r.fel != "cautare"]
			self.ales, self.sus = 0, 0
			self["stare"].setText("")
			self._arata()
			return
		self.close()

	def _inchide(self):
		self._ceas.stop()
		self._ceasDetalii.stop()
		P.uita()
		Z.scrie()
		_Postere.uita()


def deschide(session, **kwargs):
	"""Cardul "Filme si seriale" din Aplicatii (Components/HdsAplicatii.MAGAZIN_IMAGINE, 0.7.8 CR3, Eduard 18.11.2026 16:25)."""
	return session.open(HdsFilmeSeriale)


class HdsFilmPagina(Screen):
	skin = """
	<screen name="HdsFilmPagina" position="0,0" size="1920,1080" resolution="1920,1080" flags="wfNoBorder" backgroundColor="#000b1020" title="Film">
		<widget name="fundal" position="0,0" size="1920,1080" scale="1" zPosition="0" />
		<widget name="cale" position="96,40" size="900,50" font="Bold;32" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget source="global.CurrentTime" render="Label" position="1580,36" size="244,58" font="Bold;40" halign="right" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" zPosition="2">
			<convert type="ClockToText">Default</convert>
		</widget>
		<widget name="poster" position="96,330" size="260,390" zPosition="2" />
		<widget name="titlu" position="396,250" size="1430,76" font="Bold;56" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="meta" position="396,330" size="1430,42" font="Regular;30" noWrap="1" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="descriere" position="396,384" size="1260,170" font="Regular;28" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="oameni" position="396,562" size="1260,84" font="Regular;26" foregroundColor="#00aeb9cc" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="piste" position="396,652" size="1430,40" font="Regular;26" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="butoane" position="396,712" size="1430,84" zPosition="2" listOrientation="horizontal" itemWidth="430" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="stare" position="396,812" size="1430,40" font="Regular;24" foregroundColor="#00f1c40f" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="legenda" position="96,1034" size="1728,38" font="Regular;24" foregroundColor="#00aeb9cc" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="3" />
	</screen>
	"""

	def __init__(self, session, src, titlu, detalii=None):
		Screen.__init__(self, session)
		self.src, self.t, self.d = src, titlu, detalii
		self.setTitle(titlu.get("nume") or _("Film"))
		self["fundal"] = Pixmap()
		self["poster"] = Pixmap()
		for n in ("titlu", "meta", "descriere", "oameni", "piste", "stare", "legenda"):
			self[n] = Label("")
		self["cale"] = Label(textCale())
		self["butoane"] = MenuList([], content=eListboxPythonMultiContent)
		self["legenda"].setText(_("OK Alege   ·   Verde Redă   ·   Albastru Favorite   ·   EXIT Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self._ok, "cancel": self.close, "red": self.close, "green": self._reda, "blue": self._favorit,
			"left": lambda: self._muta(-1), "right": lambda: self._muta(1),
		}, -2)
		self._lucrare = ""
		self._ceas = eTimer()
		self._ceas.callback.append(self._pas)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._ceas.stop)

	def _pregateste(self):
		self.scara = self["butoane"].instance.size().width() / 1430.0
		b = self["butoane"].l
		b.setFont(0, MT.fontCod("Bold", int(28 * self.scara)))
		self._hButoane = _inaltimeRand(self["butoane"], int(84 * self.scara))
		b.setItemHeight(self._hButoane)
		self["titlu"].setText(self.t.get("nume", ""))
		if self.d is None:
			self._lucrare = V.cere("detalii", self.src.id, V.FILME, self.t["id"])
			self["stare"].setText(_(T_INCARCA))
		self._arata()
		self._ceas.start(300, False)

	def _k(self):
		cheie = (self.d or {}).get("cheie") or self.t.get("cheie") or ""
		return Z.cheie(self.src.id, cheie) if cheie else ""

	def _pas(self):
		if self._lucrare:
			rez = V.rezultat(self._lucrare)
			if rez.get("lucreaza"):
				return
			self._lucrare = ""
			if rez.get("result"):
				self.d = rez["detalii"]
				self["stare"].setText("")
			else:
				self["stare"].setText(_(rez.get("message") or V.E_NU_RASPUNDE))
			self._arata()
		self._poze()

	def _poze(self):
		d = self.d or {}
		s = self.scara
		for nume, adresa, l, h, fel in (("poster", d.get("poster") or self.t.get("poza"), int(260 * s), int(390 * s), "poster"),
				("fundal", d.get("fundal") or d.get("poster"), 960, 540, "fundal_pagina")):
			cale = P.cere(adresa, l, h, fel) if adresa else ""
			if cale and getattr(self, "_c" + nume, None) != cale:
				px = LoadPixmap(cale)
				if px:
					setattr(self, "_c" + nume, cale)
					self[nume].instance.setPixmap(px)
				else:
					P.lipsa(cale)          # stickul scos: poza se aduce din nou

	def _arata(self):
		d = self.d or {}
		self["titlu"].setText(d.get("nume") or self.t.get("nume", ""))
		self["meta"].setText(randMeta(d) if d else "")
		self["descriere"].setText(d.get("descriere", ""))
		oameni = []
		if d.get("regia"):
			oameni.append(_("Regia: %s") % d["regia"])
		if d.get("actori"):
			oameni.append(_("Actori: %s") % d["actori"])
		self["oameni"].setText("\n".join(oameni))
		st = Z.stare(self._k()) if self._k() else {}
		piste = []
		if d.get("video"):
			piste.append(_("Imagine: %s") % d["video"])
		audio = st.get("aud") or ([d["audio"]] if d.get("audio") else [])
		if audio:
			piste.append(_("Audio: %s") % ", ".join(audio))
		if st.get("sub"):
			piste.append(_("Subtitrări: %s") % ", ".join(st["sub"]))
		self["piste"].setText("   ·   ".join(piste))
		self._butoane()
		self._poze()

	def _butoane(self):
		s = self.scara
		lat = int(430 * s)
		k = self._k()
		poz = pozitieTitlu(self.src, k)
		self._actiuni = []
		if poz:
			self._actiuni.append(("continua", _("Continuă de la %s") % textOra(poz)))
			self._actiuni.append(("inceput", _("Redă de la început")))
		else:
			self._actiuni.append(("inceput", _("Redă")))
		self._actiuni.append(("favorit", _("Scoate de la favorite") if k and Z.favorit(k) else _("Adaugă la favorite")))
		d = (self.d or {}).get("durata") or 0
		intrari = []
		for fel, text in self._actiuni:
			e = [fel, MultiContentEntryRectangle(pos=(0, 0), size=(lat - int(16 * s), self._hButoane), backgroundColor=C_PANOU,
				backgroundColorSelected=C_ALES),
				MultiContentEntryText(pos=(int(16 * s), 0), size=(lat - int(48 * s),
					min(self._hButoane, MT.inaltimeCod(int(78 * s)))), font=0,
					flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=text, color=C_TEXT2, color_sel=C_TEXT)]
			if fel == "continua" and d:
				e.append(MultiContentEntryProgress(pos=(int(16 * s), int(72 * s)), size=(lat - int(48 * s), int(6 * s)),
					percent=int(min(1.0, float(poz) / d) * 100), borderWidth=0, foreColor=C_VERDE, foreColorSelected=C_VERDE,
					backColor=C_FOND, backColorSelected=C_FOND))
			intrari.append(e)
		i = self["butoane"].getSelectionIndex() if self["butoane"].list else 0
		self["butoane"].setList(intrari)
		self["butoane"].moveToIndex(min(i or 0, len(intrari) - 1))

	def _muta(self, pas):
		inst = self["butoane"].instance
		inst.moveSelection(inst.moveRight if pas > 0 else inst.moveLeft)

	def _ok(self):
		i = self["butoane"].getSelectionIndex()
		if not (0 <= i < len(self._actiuni)):
			return
		fel = self._actiuni[i][0]
		if fel == "favorit":
			self._favorit()
		else:
			self._porneste(fel == "continua")

	def _reda(self):
		self._porneste(bool(pozitieTitlu(self.src, self._k())))

	def _porneste(self, de_unde_ai_ramas):
		cheie = (self.d or {}).get("cheie") or self.t.get("cheie")
		if not cheie:
			self["stare"].setText(_(T_INCARCA))
			return
		k = Z.cheie(self.src.id, cheie)
		reda(self.session, self.src, cheie, {"nume": (self.d or {}).get("nume") or self.t.get("nume", ""),
			"poza": self.t.get("poza") or (self.d or {}).get("poster", ""), "fundal": (self.d or {}).get("fundal", ""), "tip": V.FILME},
			pozitieTitlu(self.src, k) if de_unde_ai_ramas else 0, lambda *a: self._arata())

	def _favorit(self):
		k = self._k()
		if k:
			Z.comutaFavorit(k, {"nume": (self.d or {}).get("nume") or self.t.get("nume", ""), "poza": self.t.get("poza", ""), "tip": V.FILME})
			self._butoane()


class HdsSerialPagina(Screen):
	skin = """
	<screen name="HdsSerialPagina" position="0,0" size="1920,1080" resolution="1920,1080" flags="wfNoBorder" backgroundColor="#000b1020" title="Serial">
		<widget name="fundal" position="0,0" size="1920,1080" scale="1" zPosition="0" />
		<widget name="cale" position="96,40" size="900,50" font="Bold;32" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget source="global.CurrentTime" render="Label" position="1580,36" size="244,58" font="Bold;40" halign="right" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" zPosition="2">
			<convert type="ClockToText">Default</convert>
		</widget>
		<widget name="titlu" position="60,110" size="1400,70" font="Bold;52" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="meta" position="60,184" size="1400,40" font="Regular;28" noWrap="1" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="descriere" position="60,230" size="1300,120" font="Regular;26" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="sezoane" position="52,360" size="1816,56" zPosition="2" listOrientation="horizontal" itemWidth="200" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="episoade" position="52,440" size="1816,330" zPosition="2" listOrientation="horizontal" itemWidth="360" backgroundColor="#ff000000" transparent="1" scrollbarMode="showNever" />
		<widget name="episod" position="60,790" size="1500,40" font="Bold;30" noWrap="1" foregroundColor="#00f2f4f8" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="episodText" position="60,836" size="1500,150" font="Regular;26" foregroundColor="#00c9d2e3" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="2" />
		<widget name="stare" position="1240,790" size="620,40" font="Regular;24" halign="right" foregroundColor="#00f1c40f" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="3" />
		<widget name="legenda" position="60,1036" size="1800,36" font="Regular;22" foregroundColor="#00aeb9cc" transparent="1" shadowColor="#000b1020" shadowOffset="-2,-2" zPosition="3" />
	</screen>
	"""

	def __init__(self, session, src, titlu):
		Screen.__init__(self, session)
		self.src, self.t = src, titlu
		self.d = None
		self.sezon = 0
		self.pe_sezoane = False
		self.setTitle(titlu.get("nume") or _("Serial"))
		self["fundal"] = Pixmap()
		for n in ("titlu", "meta", "descriere", "episod", "episodText", "stare", "legenda"):
			self[n] = Label("")
		self["cale"] = Label(textCale())
		self["sezoane"] = MenuList([], content=eListboxPythonMultiContent)
		self["episoade"] = MenuList([], content=eListboxPythonMultiContent)
		self["legenda"].setText(_("OK Redă   ·   SUS Sezoanele   ·   Galben Sezonul următor   ·   Albastru Favorite   ·   EXIT Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self._ok, "green": self._ok, "cancel": self.close, "red": self.close, "yellow": self._sezonUrmator,
			"blue": self._favorit, "left": lambda: self._muta(-1), "right": lambda: self._muta(1),
			"up": self._sus, "down": self._jos,
		}, -2)
		self._gen = -1
		self._ceas = eTimer()
		self._ceas.callback.append(self._pas)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._ceas.stop)

	def _pregateste(self):
		self.scara = self["episoade"].instance.size().width() / 1816.0
		s = self.scara
		z = self["sezoane"].l
		z.setFont(0, MT.fontCod("Bold", int(26 * s)))
		self._hSezoane = _inaltimeRand(self["sezoane"], int(56 * s))
		z.setItemHeight(self._hSezoane)
		self.desen = _Postere(self["episoade"], int(360 * s), int(330 * s), s, lat=True)
		self["titlu"].setText(self.t.get("nume", ""))
		self["stare"].setText(_(T_INCARCA))
		self._lucrare = V.cere("detalii", self.src.id, V.SERIALE, self.t["id"])
		self._ceas.start(300, False)

	def _pas(self):
		if self._lucrare:
			rez = V.rezultat(self._lucrare)
			if rez.get("lucreaza"):
				return
			self._lucrare = ""
			if not rez.get("result"):
				self["stare"].setText(_(rez.get("message") or V.E_NU_RASPUNDE))
				return
			self["stare"].setText("")
			self.d = rez["detalii"]
			self._alegeInceput()
			self._arata()
			return
		if self.d and P.generatie() != self._gen:
			self._gen = P.generatie()
			self.desen.fereastra(self["episoade"].getSelectionIndex(), toate=True)
			self._fundal()

	def _alegeInceput(self):
		"""Sezonul si episodul de unde continua omul (cel inceput, altfel urmatorul dupa ultimul vazut, altfel primul)."""
		sezoane = self.d.get("sezoane") or []
		self._ep = 0
		dorit = self.t.get("episod")
		ultim = None
		for si, sz in enumerate(sezoane):
			for ei, e in enumerate(sz["episoade"]):
				st = Z.stare(Z.cheie(self.src.id, e["cheie"]))
				if dorit and e["cheie"] == dorit:
					self.sezon, self._ep = si, ei
					return
				if st.get("t") and (ultim is None or st["t"] > ultim[0]):
					ultim = (st["t"], si, ei, bool(st.get("vazut")))
		if ultim:
			_t, si, ei, vazut = ultim
			if vazut and ei + 1 < len(sezoane[si]["episoade"]):
				ei += 1
			elif vazut and si + 1 < len(sezoane):
				si, ei = si + 1, 0
			self.sezon, self._ep = si, ei

	def _arata(self):
		d = self.d or {}
		s = self.scara
		self["titlu"].setText(d.get("nume") or self.t.get("nume", ""))
		sezoane = d.get("sezoane") or []
		meta = [d.get("an") or "", (_("%d sezoane") % len(sezoane)) if len(sezoane) != 1 else _("1 sezon"), textNota(d.get("nota") or ""), d.get("gen") or ""]
		self["meta"].setText("  ·  ".join(x for x in meta if x))
		self["descriere"].setText(d.get("descriere", ""))
		lat = int(200 * s)
		self["sezoane"].setList([[i, MultiContentEntryText(pos=(0, 0), size=(lat - int(12 * s), self._hSezoane), font=0,
			flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=_("Sezonul %s") % sz["numar"], color=C_ETICHETA, color_sel=C_TEXT,
			backcolor=C_FOND, backcolor_sel=C_ALES)] for i, sz in enumerate(sezoane)])
		self["sezoane"].moveToIndex(self.sezon)
		self["sezoane"].instance.setSelectionEnable(self.pe_sezoane)
		self["episoade"].instance.setSelectionEnable(not self.pe_sezoane)
		self._episoade()
		self._fundal()

	def _listaEpisoade(self):
		sezoane = (self.d or {}).get("sezoane") or []
		return sezoane[self.sezon]["episoade"] if 0 <= self.sezon < len(sezoane) else []

	def _episoade(self):
		ep = self._listaEpisoade()
		titluri = []
		for e in ep:
			titluri.append({"nume": e["nume"], "poza": e.get("poza") or "", "cheie": e["cheie"],
				"sub": ("%s. %s" % (e["numar"], e["nume"]) if e.get("numar") else e["nume"]) + ("   " + V.textDurata(e["durata"]) if e.get("durata") else "")})
		self.desen.pune(titluri, min(self._ep, max(0, len(titluri) - 1)),
			lambda t: Z.progres(Z.cheie(self.src.id, t["cheie"])) if t.get("cheie") else 0.0)
		self._infoEpisod()

	def _infoEpisod(self):
		ep = self._listaEpisoade()
		i = self["episoade"].getSelectionIndex()
		if 0 <= i < len(ep):
			e = ep[i]
			self["episod"].setText(("%s. " % e["numar"] if e.get("numar") else "") + e["nume"])
			poz = pozitieTitlu(self.src, Z.cheie(self.src.id, e["cheie"]))
			self["episodText"].setText(((_("Continuă de la %s.") % textOra(poz) + " ") if poz else "") + (e.get("descriere") or ""))
		else:
			self["episod"].setText("")
			self["episodText"].setText(_(T_GOL) if self.d else "")

	def _fundal(self):
		d = self.d or {}
		adresa = d.get("fundal") or d.get("poster") or self.t.get("poza")
		cale = P.cere(adresa, 960, 540, "fundal") if adresa else ""
		if cale and cale != getattr(self, "_cf", None):
			px = LoadPixmap(cale)
			if px:
				self._cf = cale
				self["fundal"].instance.setPixmap(px)
			else:
				P.lipsa(cale)

	def _muta(self, pas):
		if self.pe_sezoane:
			inst = self["sezoane"].instance
			inst.moveSelection(inst.moveRight if pas > 0 else inst.moveLeft)
			i = self["sezoane"].getSelectionIndex()
			if i != self.sezon:
				self.sezon, self._ep = i, 0
				self._episoade()
			return
		inst = self["episoade"].instance
		inst.moveSelection(inst.moveRight if pas > 0 else inst.moveLeft)
		self._ep = self["episoade"].getSelectionIndex()
		self.desen.fereastra(self._ep)
		self._infoEpisod()

	def _sus(self):
		if not self.pe_sezoane:
			self.pe_sezoane = True
			self._arata()

	def _jos(self):
		if self.pe_sezoane:
			self.pe_sezoane = False
			self._arata()

	def _sezonUrmator(self):
		n = len((self.d or {}).get("sezoane") or [])
		if n > 1:
			self.sezon, self._ep = (self.sezon + 1) % n, 0
			self._arata()

	def _ok(self):
		if self.pe_sezoane:
			self._jos()
			return
		ep = self._listaEpisoade()
		i = self["episoade"].getSelectionIndex()
		if not (0 <= i < len(ep)):
			return
		e = ep[i]
		d = self.d or {}
		sz = d["sezoane"][self.sezon]
		meta = {"nume": e["nume"], "poza": e.get("poza") or self.t.get("poza", ""), "tip": V.SERIALE, "serial": self.t["id"],
			"serial_nume": d.get("nume") or self.t.get("nume", ""), "sezon": sz["numar"], "numar": e.get("numar", "")}
		urmatoare = [(x["cheie"], dict(meta, nume=x["nume"], numar=x.get("numar", ""))) for x in ep[i + 1:i + 30]]
		reda(self.session, self.src, e["cheie"], meta, pozitieTitlu(self.src, Z.cheie(self.src.id, e["cheie"])), lambda *a: self._arata(), urmatoare)

	def _favorit(self):
		k = Z.cheie(self.src.id, "s" + self.t["id"])
		acum = Z.comutaFavorit(k, {"nume": (self.d or {}).get("nume") or self.t.get("nume", ""), "poza": self.t.get("poza", ""), "tip": V.SERIALE})
		self["stare"].setText(_("Adăugat la favorite.") if acum else _("Scos de la favorite."))


# ------------------------------------------------------------------ redarea

def pozitieTitlu(src, k):
	"""De unde continua titlul: pozitia de pe server (Emby/Jellyfin, vazut si pe alt aparat), altfel cea tinuta aici."""
	if not k:
		return 0
	if src is not None and src.continuaPeServer:
		p = src.pozitieServer(k.split("/", 1)[1])
		if p is not None:
			return p
	return Z.pozitie(k)


def reda(session, src, cheie, meta, de_la_s=0, dupa=None, urmatoare=None):
	ref = src.referinta(cheie)
	if not ref:
		return
	serviciu = eServiceReference(ref)
	serviciu.setName(meta.get("nume") or cheie)
	if dupa:
		session.openWithCallback(dupa, HdsVodPlayer, serviciu, Z.cheie(src.id, cheie), meta, de_la_s, src, urmatoare)
	else:
		session.open(HdsVodPlayer, serviciu, Z.cheie(src.id, cheie), meta, de_la_s, src, urmatoare)


# the picture of wide films on Broadcom: Components/HdsAspectFilm (moved there for the channel list too, AIP0)
from Components.HdsAspectFilm import aspectFereastra, AspectFilm, comun as aspectComun  # noqa: F401


class HdsVodPlayer(MoviePlayer):
	"""Playerul de filme, pentru un film sau episod din internet: porneste de unde ai ramas, tine minte pozitia (in memorie la
	30 s, pe flash cel mult o data la 5 minute si la oprire), pistele audio si subtitrarile vazute, si se inchide fara
	intrebare (EXIT sau sfarsitul filmului). La un episod terminat porneste singur urmatorul din acelasi sezon.
	Alegerea subtitrarii si a sunetului o face, ca la orice flux, HdsPisteLimbi (limba preferata, apoi ce ai ales de mana pe
	acest film)."""
	ENABLE_RESUME_SUPPORT = False

	def __init__(self, session, serviciu, k, meta, de_la_s=0, src=None, urmatoare=None):
		self.hdsK, self.hdsMeta, self.hdsDeLa = k, dict(meta or {}), int(de_la_s or 0)
		self.hdsRef = serviciu.toString()
		self.hdsSrc, self.hdsUrmatoare = src, list(urmatoare or [])
		self.hdsCautat = not self.hdsDeLa
		self.hdsIncercari = 0
		MoviePlayer.__init__(self, session, serviciu)
		self.skinName = "MoviePlayer"
		self.hdsAspect = aspectComun()     # the same as the channel list's (Components/HdsAspectFilm, AIP0)
		self.hdsCeasVod = eTimer()
		self.hdsCeasVod.callback.append(self.hdsPasVod)
		self.hdsCeasVod.start(1000, False)
		self.onClose.append(self.hdsLaInchidere)
		self.onExecBegin.append(self.hdsAspect.reaplica)

	def hdsPasAspect(self):
		"""the window of a wide film on Broadcom (AspectFilm), read again every second: the size can come late"""
		try:
			from enigma import iServiceInformation
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			s = self.session.nav.getCurrentService()
			info = s and s.info()
			if ref is None or ref.type != 4097 or not info:
				self.hdsAspect.pas(False, 0, 0, 0)
				return
			self.hdsAspect.pas(True, info.getInfo(iServiceInformation.sVideoWidth), info.getInfo(iServiceInformation.sVideoHeight),
				info.getInfo(iServiceInformation.sAspect))
		except Exception as e:
			print("[HdsVodPlayer] aspect: %s" % type(e).__name__)

	def hdsVerificaCanalul(self):
		# filmul nostru e o referinta fara cale de disc: nu e un „canal pornit peste film”
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is not None and ref.toString() == self.hdsRef:
			self.hdsCanalPeste = False
			return
		MoviePlayer.hdsVerificaCanalul(self)

	def hdsPozitie(self):
		s = self.session.nav.getCurrentService()
		cautare = s and s.seek()
		if not cautare:
			return None, None
		p, l = cautare.getPlayPosition(), cautare.getLength()
		poz = p[1] // 90000 if p and not p[0] else None
		lung = l[1] // 90000 if l and not l[0] and l[1] > 0 else None
		return poz, lung

	def hdsPasVod(self):
		self.hdsPasAspect()
		poz, lung = self.hdsPozitie()
		if not self.hdsCautat:
			self.hdsIncercari += 1
			s = self.session.nav.getCurrentService()
			cautare = s and s.seek()
			if cautare and lung and cautare.isCurrentlySeekable():
				cautare.seekTo(int(self.hdsDeLa) * 90000)
				self.hdsCautat = True
			elif self.hdsIncercari > 30:
				self.hdsCautat = True
			return
		if poz is not None and self.hdsIncercari % 30 == 0:
			Z.noteaza(self.hdsK, poz, lung, self.hdsMeta)
			self.hdsServer(poz, lung, "progres" if getattr(self, "hdsPornitServer", False) else "start")
		self.hdsIncercari += 1
		if poz is not None:
			self.hdsUltima = (poz, lung)

	def hdsServer(self, poz, lung, fel):
		"""Sursa afla unde ai ajuns: serverele Emby/Jellyfin tin pozitia (pe firul lor), discul face imaginea din film."""
		src = self.hdsSrc
		if src is None:
			return
		cheie = self.hdsK.split("/", 1)[1]
		if fel == "start":
			self.hdsPornitServer = True
		elif fel == "oprit":
			if not getattr(self, "hdsPornitServer", False):
				# iesire inainte de primul anunt: serverul tot opreste transcodarea pornita de releu (fara pozitie trimisa)
				inchisa = getattr(src, "redareInchisa", None)
				if inchisa is not None:
					try:
						inchisa(cheie)
					except Exception as e:
						print("[HdsVodPlayer] sursa: %s" % type(e).__name__)
				return
			self.hdsPornitServer = False
		try:
			src.progres(cheie, poz, lung, fel)
			if fel != "oprit":
				src.inRedare(cheie, poz, lung)
		except Exception as e:
			print("[HdsVodPlayer] sursa: %s" % type(e).__name__)

	def hdsPiste(self):
		s = self.session.nav.getCurrentService()
		sub, aud = [], []
		try:
			lista = s and s.subtitle() and s.subtitle().getSubtitleList() or []
			for x in lista:
				limba = str(x[4] if len(x) > 4 else "").strip()
				if limba and limba not in sub:
					sub.append(limba)
		except Exception:
			pass
		try:
			a = s and s.audioTracks()
			for i in range(a.getNumberOfTracks() if a else 0):
				info = a.getTrackInfo(i)
				t = " ".join(x for x in (info.getLanguage(), info.getDescription()) if x).strip()
				if t and t not in aud:
					aud.append(t)
		except Exception:
			pass
		return sub, aud

	def hdsSalveaza(self):
		poz, lung = self.hdsPozitie()
		if poz is None:
			poz, lung = getattr(self, "hdsUltima", (None, None))
		if poz is None:
			return
		sub, aud = self.hdsPiste()
		Z.noteaza(self.hdsK, poz, lung, self.hdsMeta, subtitrari=sub or None, audio=aud or None, forteaza=True)
		self.hdsServer(poz, lung, "oprit")

	def leavePlayer(self):
		self.hdsSalveaza()
		self.leavePlayerConfirmed([True, "quit"])

	def handleLeave(self, how):
		# fara „Oprești redarea?”: pozitia ramane, deci oprirea nu pierde nimic (regula cat mai simplu)
		self.is_closing = True
		self.hdsSalveaza()
		self.leavePlayerConfirmed([True, "quit"])

	def hdsIesirePrivire(self):
		"""EXIT: cu bara la vedere o ascunde, altfel iese din film (pozitia ramane), oricare ar fi alegerea „EXIT la film” a
		receptorului: la un film din internet nu exista lista de filme in care sa te intorci (proba pe receptorul de probe, 13.11: EXIT doar ascundea bara)."""
		if not self.execing or self.session.current_dialog is not self:
			return 0
		if self.shown:
			self.hide()
		else:
			self.handleLeave("quit")
		return 1

	def doEofInternal(self, playing):
		if not self.execing or not playing:
			return
		poz, lung = self.hdsPozitie()
		Z.noteaza(self.hdsK, lung or poz or 0, lung, self.hdsMeta, forteaza=True)
		self.hdsServer(lung or poz or 0, lung, "oprit")
		if self.hdsUrmatoare and self.hdsSrc is not None:
			cheie, meta = self.hdsUrmatoare.pop(0)
			ref = self.hdsSrc.referinta(cheie)
			if ref:
				serviciu = eServiceReference(ref)
				serviciu.setName(meta.get("nume") or cheie)
				self.hdsK, self.hdsMeta, self.hdsRef = Z.cheie(self.hdsSrc.id, cheie), meta, serviciu.toString()
				self.hdsDeLa, self.hdsCautat, self.hdsIncercari = 0, True, 0
				self.session.nav.playService(serviciu)
				return
		self.leavePlayerConfirmed([True, "quit"])

	def hdsLaInchidere(self):
		self.hdsCeasVod.stop()
		self.hdsAspect.laSfarsit()
		Z.scrie()
