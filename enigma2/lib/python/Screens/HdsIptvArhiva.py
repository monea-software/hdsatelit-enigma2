# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvArhiva (0.7.5): „Emisiunile trecute” ale unui canal de internet care are arhiva la furnizor (Xtream, tv_archive). Se deschide
# din lista de canale: MENU pe canal > „Emisiunile trecute”, randul apare numai la canalele cu arhiva. Un singur ecran: emisiunile din
# arhiva, cea mai noua sus (si cea de acum, de la inceput), descrierea celei alese, OK sau VERDE o porneste. Inapoi la televizorul in
# direct: canalul ales din nou in lista.
# Lista se cere serverului NUMAI cand se deschide ecranul, pe un fir (Components/HdsIptvClient.programeArhiva); nimic in fundal.
# Redarea trece prin releu (Components/HdsIptvAdrese.py) cu cheia a<id>-<AAAALLZZHHMM>-<minute>: parola nu intra in referinta.
# Optional: config.usage.hds_iptv_arhiva (Da din fabrica; Meniu > Setari > Surse Internet > functii, web /setari?id=hds_iptv_functii).
# Pereche web: /iptv, sectiunea „Emisiunile trecute” a canalului de pe televizor (HdsWebControl/internet_web.py, /api/iptv-arhiva).
# Partea de sus (fara enigma2) se probeaza pe PC: depozitul de unelte, teste/test_iptv_ipi_075.py.

import os
import threading
import time

from Components import HdsIptvSurse as I
from Components.HdsIptvSurse import N_

T_TITLU = N_("Emisiunile trecute")
T_SE_ADUCE = N_("Se aduce lista emisiunilor din arhivă...")
T_GOL = N_("Furnizorul nu are acum nicio emisiune în arhivă pentru acest canal.")
T_STARE = N_("%d emisiuni în arhivă (%d zile). OK pornește emisiunea aleasă.")
T_ACUM = N_("acum, de la început")
T_PORNESTE = N_("Pornește")
T_FARA_ARHIVA = N_("Canalul nu are arhivă la furnizor.")

_ZILE = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_lacat = threading.Lock()
_arhive = {}    # sursa -> (semnul fisierului, {cheie: zile}); numai canalele cu arhiva, deci putin


def _t(text):
	try:
		return _(text)
	except NameError:  # probele de pe PC
		return text


def _semn(sid):
	try:
		st = os.stat(os.path.join(I.DOSAR, "canale-%s.json" % sid))
		return (st.st_mtime, st.st_size, st.st_ino)
	except OSError:
		return None


def zileCanal(sid, cheie):
	"""Zilele de arhiva ale canalului (campul „arhiva” pus la improspatarea listei), 0 fara arhiva. Lista sursei se citeste o data pe
	fisier si se tin minte numai canalele cu arhiva."""
	semn = _semn(sid)
	if semn is None:
		return 0
	with _lacat:
		v = _arhive.get(sid)
	if v is None or v[0] != semn:
		harta = {}
		for c in I.citesteCanale(sid):
			if isinstance(c, list) and len(c) > 4 and isinstance(c[4], dict) and c[4].get("arhiva"):
				try:
					harta[c[0]] = int(c[4]["arhiva"])
				except (TypeError, ValueError):
					pass
		with _lacat:
			if len(_arhive) > 8:
				_arhive.clear()
			_arhive[sid] = v = (semn, harta)
	return v[1].get(cheie, 0)


def activ():
	try:
		from Components.config import config
		return bool(config.usage.hds_iptv_arhiva.value)
	except (AttributeError, KeyError, ImportError):
		return True


def canalCuArhiva(ref_text):
	"""(sursa, sid, cheie, zile) pentru un canal Xtream de aici cu arhiva, altfel None. O emisiune din arhiva care se reda (cheia a<id>-...)
	da canalul ei (l<id>). Fara cereri in retea."""
	if not ref_text or not activ():
		return None
	sid, cheie = I.desparteCale(ref_text)
	if sid is not None and cheie and cheie[0] == "a" and "-" in cheie:
		cheie = "l" + cheie[1:cheie.index("-")]
	if sid is None or not cheie or cheie[0] != "l":
		return None
	s = I.sursa(sid)
	if s is None or s.get("fel") != "xtream":
		return None
	zile = zileCanal(sid, cheie)
	return (s, sid, cheie, zile) if zile else None


def textZi(ts, acum=None):
	"""„Azi”, „Ieri” sau „Lun 10.11” (ora receptorului)."""
	acum = time.time() if acum is None else acum
	zi = time.localtime(ts)
	azi = time.localtime(acum)
	dif = (time.mktime((azi.tm_year, azi.tm_mon, azi.tm_mday, 0, 0, 0, 0, 0, -1)) -
		time.mktime((zi.tm_year, zi.tm_mon, zi.tm_mday, 0, 0, 0, 0, 0, -1)))
	zile = int(round(dif / 86400.0))
	if zile == 0:
		return _t("Today")
	if zile == 1:
		return _t("Yesterday")
	return "%s %02d.%02d" % (_t(_ZILE[zi.tm_wday]), zi.tm_mday, zi.tm_mon)


def randProgram(p, acum=None):
	"""Un rand al listei: „Azi 19:00-20:00  Titlu” (si „acum, de la inceput” la emisiunea de acum)."""
	a, b = time.localtime(p["inceput"]), time.localtime(p["sfarsit"])
	rand = "%s %02d:%02d-%02d:%02d  %s" % (textZi(p["inceput"], acum), a.tm_hour, a.tm_min, b.tm_hour, b.tm_min, p.get("titlu") or "-")
	if p.get("acum"):
		rand += " (%s)" % _t(T_ACUM)
	return rand


def numeArhiva(nume_canal, p, acum=None):
	"""Numele aratat pe bara cat se reda emisiunea: „Canal · Titlu (Azi 19:00)”."""
	a = time.localtime(p["inceput"])
	# doua puncte in nume merg (numele e restul referintei, ca la „RO: PRO TV”)
	return "%s · %s (%s %02d:%02d)" % (nume_canal or "", p.get("titlu") or "-", textZi(p["inceput"], acum), a.tm_hour, a.tm_min)


def numeCanal(ref_text, sid, cheie):
	"""Numele canalului pentru titlu si web: din referinta (la o emisiune din arhiva, partea dinainte de „ · ”), altfel din grupele lui."""
	parti = (ref_text or "").split(":", 10)
	nume = ""
	if len(parti) > 10 and ":" in parti[10]:
		nume = parti[10].split(":", 1)[1].split(" · ", 1)[0].strip()
	if not nume:
		din_buchete = getattr(I, "numeDinBuchete", None)   # 0.7.5 (IPT); fara el, cheia
		nume = din_buchete(I.caleCanal(sid, cheie)) if din_buchete is not None else ""
	return nume or cheie


def refArhiva(ref_canal_text, sid, cheie_arhiva, nume):
	"""Referinta de redare a emisiunii: acelasi player ca al canalului (4097/5001/5002), numere proprii (bara nu arata ghidul canalului
	in direct peste emisiunea veche), calea releului cu cheia emisiunii, numele la coada."""
	tip = (ref_canal_text or "4097").split(":", 1)[0]
	if not tip.isdigit():
		tip = "4097"
	ref = I.refCanal(sid, cheie_arhiva)
	return tip + ref[ref.index(":"):] + (nume or "").replace("\n", " ")


class _Cerere(object):
	"""Lista emisiunilor ceruta pe un fir; ecranul se uita la ea cu un ceas (fara apeluri din fir in enigma2)."""

	def __init__(self, s, cheie):
		self.rez = None
		self.eroare = None
		self.gata = False
		fir = threading.Thread(target=self._lucru, args=(s, cheie), name="HdsIptvArhiva")
		fir.daemon = True
		fir.start()

	def _lucru(self, s, cheie):
		from Components import HdsIptvClient as C
		try:
			self.rez = C.programeArhiva(s, cheie)
		except C.EroareIptv as e:
			self.eroare = e.pentruOm()
		except Exception as e:
			# numai felul erorii: textul ar putea cuprinde adresa
			print("[HdsIptvArhiva] %s" % type(e).__name__)
			self.eroare = C.E_NU_RASPUNDE
		self.gata = True


try:
	import enigma  # noqa: F401 (pe PC lipseste: Screens.Screen nu se incarca acolo, iar partea de sus se probeaza fara el)
	from Screens.Screen import Screen
except ImportError:  # probele de pe PC
	Screen = object


class HdsIptvArhiva(Screen):
	skin = """
	<screen name="HdsIptvArhiva" resolution="1920,1080" position="center,center" size="1500,860" title="Emisiunile trecute">
		<widget name="stare" position="30,20" size="1440,50" font="Regular;30" />
		<widget name="lista" position="30,85" size="1440,560" font="Regular;30" itemHeight="46" scrollbarMode="showOnDemand" />
		<widget name="descriere" position="30,660" size="1440,120" font="Regular;26" />
		<widget name="key_green" position="30,795" size="340,50" zPosition="1" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session, ref, nume_canal=""):
		Screen.__init__(self, session)
		from Components.ActionMap import ActionMap
		from Components.Button import Button
		from Components.Label import Label
		from Components.MenuList import MenuList
		self.ref_text = ref.toString() if hasattr(ref, "toString") else str(ref or "")
		self.nume_canal = nume_canal
		self.setTitle("%s: %s" % (_t(T_TITLU), nume_canal) if nume_canal else _t(T_TITLU))
		self["stare"] = Label(_t(T_SE_ADUCE))
		self["lista"] = MenuList([])
		self["descriere"] = Label("")
		self["key_green"] = Button(_t(T_PORNESTE))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": lambda: self.close(False),
			"ok": self.porneste,
			"green": self.porneste,
		}, -1)
		self.programe = []
		self.canal = canalCuArhiva(self.ref_text)
		self.cerere = None
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._uita)
		self.onClose.append(self.ceas.stop)
		self.onLayoutFinish.append(self._incepe)

	def _incepe(self):
		self["lista"].onSelectionChanged.append(self._descriere)
		if self.canal is None:
			self["stare"].setText(_t(T_FARA_ARHIVA))
			return
		self.cerere = _Cerere(self.canal[0], self.canal[2])
		self.ceas.start(300, False)

	def _uita(self):
		c = self.cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		if c.eroare:
			self["stare"].setText(_t(c.eroare))
			return
		acum = time.time()
		self.programe = c.rez or []
		if not self.programe:
			self["stare"].setText(_t(T_GOL))
			return
		self["stare"].setText(_t(T_STARE) % (len(self.programe), self.canal[3]))
		self["lista"].setList([(randProgram(p, acum), i) for i, p in enumerate(self.programe)])
		self._descriere()

	def _ales(self):
		cur = self["lista"].getCurrent()
		return self.programe[cur[1]] if cur and 0 <= cur[1] < len(self.programe) else None

	def _descriere(self):
		p = self._ales()
		self["descriere"].setText(p.get("descriere") or "" if p else "")

	def porneste(self):
		p = self._ales()
		if p is None or self.canal is None:
			return
		from enigma import eServiceReference
		ref = refArhiva(self.ref_text, self.canal[1], p["cheie"], numeArhiva(self.nume_canal, p))
		self.session.nav.playService(eServiceReference(ref))
		self.close(True)
