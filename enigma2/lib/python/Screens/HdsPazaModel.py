# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPazaModel.py (ecranul): diagnosticul pornirii pe televizor (Components/HdsDiagnostic.py). Apare singur, in locul
# interfetei, numai cand pornirea nu reuseste: imaginea ruleaza pe alt receptor decat cel pentru care e construita, sau
# amprenta receptorului nu se poate citi (Components/HdsPazaModel.py). Garda din enigma2.sh a oprit deja carligul
# trusei; showiframe (el da imaginea pe HDMI si drumul tastelor telecomenzii) l-a pornit numai daca stie ca nu scrie
# nimic pe receptor (cu UPD_PATH-ul etichetei pus in /proc/stb/info/upd_path, vezi garda). Cand showiframe nu a pornit,
# pe un receptor adevarat e posibil ca ecranul sa nu se vada; aceleasi date raman in interfata web (/paza-model), iar
# codul pe afisajul din fata.
# Cand receptorul porneste normal, ecranul nu apare; acelasi ecran se deschide din Meniu > Informatii despre sistem >
# Diagnosticul pornirii (HdsDiagnosticPornire), unde OK si EXIT il inchid.
#
# Gandit pentru o poza facuta televizorului cu telefonul: de sus in jos titlul si software-ul, codul principal mare in
# caseta din dreapta sus, ce inseamna codul, tabelul cu ce a citit receptorul fata de ce cere software-ul (cate un rand
# pe cheie, valoarea colorata dupa stare si codul randului), apoi rugamintea (poza spre forum sau spre
# contact@hdsatelit.com), adresa paginii web, ce poate face omul si codul QR (adresa paginii web; fara adresa in retea,
# un e-mail spre noi cu codul in subiect). Pe televizor nu intra listele de partitii (numai numarul si prima diferenta)
# si nici jurnalele: ele sunt in pagina web. Adresa se afla fara sa se trimita nimic in retea; cat timp reteaua nu are
# inca adresa, se incearca din nou la 5 s, iar codul QR se deseneaza din nou cand vine adresa.
#
# Fereastra pornirii nu se inchide: OK si EXIT nu fac nimic (interfata nu porneste mai departe pe alt receptor). Tasta
# de pornire trece prin actiunile globale din mytest.py (PowerKey), care cer ALLOW_SUSPEND: apasarea scurta duce in
# standby (sau opreste, dupa setare), iar cea lunga face ce spune setarea ei, pe acelasi drum ca pe InfoBar.
#
# Skinul: facut la deschidere dupa marimea ecranului (asezarea e gandita pe 1920x1080) si dupa randuri (culoarea
# fiecarei valori), numai cu fontul „Regular” si culori scrise direct, ca sa arate la fel in orice skin. Ecranul cauta
# numele NUME_SKIN, pe care niciun skin nu il are: skinurile de dinainte (si skinul cu care se construieste o arhiva
# alfa) au o forma veche <screen name="HdsPazaModel">, numai cu titlul si o fraza, care altfel ar avea intaietate. Valorile au 36 px la 1920x1080, codul 112 px; lungimile sunt masurate pe cele 13 limbi.
#
# HdsPazaModelRefuz: fereastra refuzului unui pachet in actualizarea din meniu (Screens/HdsSoftwareUpdate.py); textul
# simplu sus, randurile tehnice mai mic, dedesubt, si OK sau EXIT o inchide. HdsPazaModelIntrebare: intrebarile aceluiasi
# ecran (verificarea pachetului, ultima confirmare), cu „Da” / „Nu” alese cu sagetile si OK. Fereastra de mesaj a
# skinului HDSatelit are loc numai pentru trei randuri, iar aceste texte au mai multe.

from enigma import eTimer, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
try:
	from Components.Sources.CanvasSource import CanvasSource
except ImportError:  # probele de pe PC fara Canvas
	CanvasSource = None

PAGINA_WEB = "/paza-model"
PORT_WEB_IMPLICIT = 80
# portul pe care asculta interfata web, scris de HdsWebControl la pornire (8080 cand 80 era ocupat)
CALE_PORT_ACUM = "/var/run/hdswebcontrol.port"
INTERVAL_ADRESA_MS = 5000
INCERCARI_ADRESA = 36

# culorile (0x00RRGGBB in skin): fundalul, chihlimbarul casetei codului, etichetele, valorile dupa stare
FUNDAL = "#00101828"
CHIHLIMBAR = "#00f5b83d"
TEXT = "#00f2f4f8"
SLAB = "#00aab4c4"
CULORI_STARE = {
	"bun": "#00a8e6b4",
	"rau": "#00ff8a7a",
	"necitit": "#00ff8a7a",
	"avertisment": "#00f5b83d",
	"info": "#00f2f4f8",
}
# cate semne incap in coloanele valorilor (36 px, fontul Regular al skinului HDSatelit: ~19,5 px pe semn)
MAX_CITIT = 32
MAX_CERUT = 29
RANDURI_MAX = 9
# numele cautat in skinuri: niciun skin nu il are, deci enigma2 ia mereu skinul facut aici (forma veche
# <screen name="HdsPazaModel"> din skinurile de dinainte, cu titlu si o fraza, nu se mai foloseste)
NUME_SKIN = "HdsDiagnosticPornireEcran"


def _scara(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	return x, y


def skinEcran(latime, inaltime, stari=None, cu_cod=True, cu_qr=True):
	"""Skinul pe tot ecranul, socotit pentru `latime` x `inaltime` (asezarea e gandita pe 1920x1080). `stari`: starea
	fiecarui rand al tabelului (culoarea valorii citite; cel mult RANDURI_MAX); cu_cod: caseta codului; cu_qr: locul
	codului QR (numai cand exista CanvasSource)."""
	x, y = _scara(latime, inaltime)
	stari = list(stari or [])[:RANDURI_MAX]
	stari += ["info"] * (RANDURI_MAX - len(stari))
	v = {"l": latime, "h": inaltime, "fundal": FUNDAL, "chihlimbar": CHIHLIMBAR, "text": TEXT, "slab": SLAB,
		"mx": x(80), "cl": x(1760), "linie": max(2, y(4))}
	bucati = ["""
	<screen name="%(nume)s" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="%(fundal)s" title="Diagnosticul pornirii">""" % dict(v, nume=NUME_SKIN)]

	def eticheta(sursa, px, py, pl, ph, font, culoare, halign="left", valign="center", z=1):
		bucati.append('\n\t\t<widget source="%s" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
			'halign="%s" valign="%s" foregroundColor="%s" backgroundColor="%s" transparent="1" zPosition="%d" />' % (
				sursa, x(px), y(py), x(pl), y(ph), y(font), halign, valign, culoare, FUNDAL, z))
	lat_titlu = 1320 if cu_cod else 1760
	eticheta("titlu", 80, 34, lat_titlu, 76, 54, "#00ffffff")
	eticheta("software", 80, 112, lat_titlu, 44, 30, SLAB)
	if cu_cod:
		bucati.append('\n\t\t<eLabel position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="1" />' % (
			x(1440), y(28), x(400), y(168), CHIHLIMBAR))
		bucati.append('\n\t\t<widget source="cod_eticheta" render="Label" position="%d,%d" size="%d,%d" '
			'font="Regular;%d" halign="center" valign="center" foregroundColor="%s" backgroundColor="%s" '
			'transparent="1" zPosition="2" />' % (x(1440), y(34), x(400), y(34), y(28), FUNDAL, CHIHLIMBAR))
		bucati.append('\n\t\t<widget source="cod" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
			'halign="center" valign="center" foregroundColor="%s" backgroundColor="%s" transparent="1" '
			'zPosition="2" />' % (x(1440), y(66), x(400), y(124), y(112), FUNDAL, CHIHLIMBAR))
	bucati.append('\n\t\t<eLabel position="%(mx)d,%(ly)d" size="%(cl)d,%(linie)d" backgroundColor="%(chihlimbar)s" '
		'zPosition="1" />' % dict(v, ly=y(206)))
	eticheta("mesaj", 80, 222, 1760, 96, 33, TEXT, valign="top")
	eticheta("h_citit", 500, 318, 640, 36, 26, SLAB)
	eticheta("h_cerut", 1160, 318, 580, 36, 26, SLAB)
	eticheta("h_cod", 1750, 318, 90, 36, 26, SLAB)
	for i, stare in enumerate(stari):
		ry = 356 + 48 * i
		eticheta("r%d_e" % i, 80, ry, 410, 46, 34, SLAB)
		eticheta("r%d_g" % i, 500, ry, 640, 46, 36, CULORI_STARE.get(stare, TEXT))
		eticheta("r%d_a" % i, 1160, ry, 580, 46, 36, TEXT)
		eticheta("r%d_c" % i, 1750, ry, 90, 46, 28, CULORI_STARE["rau"])
	lat_jos = 1480 if (cu_qr and CanvasSource is not None) else 1760
	eticheta("rugaminte", 80, 786, lat_jos, 96, 33, "#00ffffff", valign="top")
	eticheta("nota", 80, 886, lat_jos, 46, 34, TEXT)
	eticheta("cefaci", 80, 936, lat_jos, 112, 28, SLAB, valign="top")
	if cu_qr and CanvasSource is not None:
		bucati.append('\n\t\t<widget source="qr" render="Canvas" position="%d,%d" size="%d,%d" zPosition="2" />' % (
			x(1600), y(800), min(x(240), y(240)), min(x(240), y(240))))
	bucati.append("\n\t</screen>")
	return "".join(bucati)


def portWeb():
	"""Portul pe care asculta interfata web (CALE_PORT_ACUM), apoi setarea pluginului HdsWebControl, apoi cel implicit"""
	try:
		with open(CALE_PORT_ACUM, encoding="ascii") as f:
			port = int(f.read(16).strip())
		if 0 < port < 65536:
			return port
	except (IOError, OSError, ValueError):
		pass
	try:
		from Components.config import config
		return int(config.plugins.hdswebcontrol.port.value)
	except Exception:
		return PORT_WEB_IMPLICIT


def adresaIp():
	"""Adresa IPv4 a receptorului in reteaua locala, sau "". Intai interfata rutei implicite (un connect UDP numai
	alege ruta, nu trimite nimic), apoi eth0 si wlan0 citite din nucleu (SIOCGIFADDR)."""
	import socket
	ip = ""
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect(("192.0.2.1", 9))
			ip = s.getsockname()[0]
		finally:
			s.close()
	except (OSError, socket.error, ValueError):
		ip = ""
	if not ip or ip.startswith("0.") or ip.startswith("127."):
		ip = ""
		try:
			import fcntl
			import struct
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			try:
				for nume in ("eth0", "wlan0"):
					try:
						date = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", nume.encode("ascii")))
						ip = socket.inet_ntoa(date[20:24])
						break
					except (OSError, IOError):
						continue
			finally:
				s.close()
		except (ImportError, OSError, socket.error):
			ip = ""
	return ip if ip and not ip.startswith("0.") and not ip.startswith("127.") else ""


def adresaWeb(ip=None, port=None):
	"""http://<ip>[:port]/paza-model, sau "" cat timp receptorul nu are adresa in retea"""
	ip = adresaIp() if ip is None else ip
	if not ip:
		return ""
	port = portWeb() if port is None else port
	return "http://%s%s%s" % (ip, "" if port == 80 else ":%d" % port, PAGINA_WEB)


def textNota(adresa):
	"""Randul cu adresa paginii web (Components/HdsDiagnostic.textAdresa)"""
	from Components import HdsDiagnostic
	return HdsDiagnostic.textAdresa(adresa)


def texte(verdict, adresa="", din_meniu=False):
	"""Textele ecranului din verdictul lui Components.HdsPazaModel.verdict(): {titlu, software, cod, mesaj, rugaminte,
	nota, cefaci, coduri, randuri (pentru televizor)}"""
	from Components import HdsDiagnostic as D
	from Components import HdsPazaModel as M
	coduri = D.coduri(verdict)
	cod = coduri[0] if coduri else ""
	if din_meniu:
		titlu = _(D.TITLU_MENIU)
	else:
		titlu = D.titluCod(cod) if cod else M.mesajStare(verdict)[0]
	if cod:
		mesaj = D.textCod(cod)
		if len(coduri) > 1:
			mesaj += " " + _("Alte coduri: %s.") % ", ".join(coduri[1:])
	elif verdict.get("stare") == M.STARE_POTRIVIT and verdict.get("avertismente"):
		mesaj = _("Pornirea a reușit. Câteva valori diferă de cele așteptate: modelul nu este încă confirmat.")
	elif verdict.get("stare") == M.STARE_POTRIVIT:
		mesaj = _("Pornirea a reușit: receptorul se potrivește cu software-ul.")
	else:
		mesaj = M.mesajStare(verdict)[1][0]
	if din_meniu:
		cefaci = _("OK sau EXIT închide fereastra.")
	else:
		cefaci = D.ceFaci()
	return {"titlu": titlu, "software": D.software(verdict), "cod": cod, "coduri": coduri, "mesaj": mesaj,
		"rugaminte": D.rugaminte() if cod else "", "nota": D.textAdresa(adresa), "cefaci": cefaci,
		"randuri": D.randuri(verdict, tv=True)[:RANDURI_MAX]}


def textePazaVechi(verdict, adresa="", din_meniu=False):
	"""Rezerva lui texte(), daca diagnosticul cade (verdict neasteptat): mesajul pazei de model ca inainte, fara cod
	si fara tabel, ca ecranul sa se vada oricum"""
	titlu, fraze, tehnice = "", [], []
	try:
		from Components import HdsPazaModel as M
		titlu, fraze, tehnice = M.mesajStare(verdict or {})
	except Exception as eroare:
		print("[HdsPazaModel] mesajul pazei: %s" % eroare)
	adresa_text = ""
	try:
		adresa_text = textNota(adresa)
	except Exception:
		adresa_text = adresa
	return {"titlu": titlu or "HD Satelit", "software": "", "cod": "", "coduri": [], "mesaj": " ".join(fraze[:2]),
		"rugaminte": "\n".join(tehnice[:2]), "nota": adresa_text,
		"cefaci": _("OK sau EXIT închide fereastra.") if din_meniu else " ".join(fraze[2:]), "randuri": []}


def deseneazaQr(ecran, sursa, text):
	"""Codul QR al textului pe CanvasSource-ul `sursa` (marimea din widget), sau locul gol. -> True daca s-a desenat"""
	try:
		c = ecran[sursa]
	except (KeyError, TypeError):
		return False
	latime = inaltime = 0
	for r in getattr(ecran, "renderer", []) or []:
		if getattr(r, "source", None) is c and getattr(r, "instance", None) is not None:
			latime, inaltime = r.instance.size().width(), r.instance.size().height()
	if not latime:
		return False
	try:
		if text:
			from Components.HdsQr import deseneaza
			deseneaza(c, text, latime, inaltime)
		else:
			c.clear()
			c.fill(0, 0, latime, inaltime, 0x00101828)
		c.flush()
		return True
	except Exception as eroare:
		print("[HdsPazaModel] codul QR: %s" % eroare)
		return False


def skinRefuz(latime, inaltime):
	"""Fereastra refuzului, in mijlocul ecranului, socotita pentru `latime` x `inaltime` (asezarea pe 1920x1080)."""
	x, y = _scara(latime, inaltime)
	fl, fh = x(1400), y(800)
	return """
	<screen name="HdsPazaModelRefuz" position="center,center" size="%(fl)d,%(fh)d" flags="wfNoBorder" backgroundColor="#00101828" title="Pachetul nu se scrie">
		<eLabel position="0,0" size="%(fl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="tehnic" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(ef)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"fl": fl, "fh": fh, "linie": max(2, y(4)), "mx": x(50), "cl": fl - 2 * x(50),
		"ty": y(25), "th": y(65), "tf": y(44),
		"my": y(105), "mh": y(330), "mf": y(30),
		"ey": y(445), "eh": y(275), "ef": y(24),
		"ny": y(735), "nh": y(45),
	}


def texteRefuz(text):
	"""(mesaj, tehnic) din textul lui Components.HdsPazaModel.textRefuz: randurile tehnice vin dupa un rand gol"""
	parti = (text or "").split("\n\n", 1)
	return parti[0], (parti[1] if len(parti) > 1 else "")


def skinIntrebare(latime, inaltime, randuri_mesaj=9, randuri_tehnic=6):
	"""Fereastra unei intrebari cu „Da” / „Nu”, in mijlocul ecranului: titlul, textul (cel mult `randuri_mesaj`
	randuri), randurile tehnice mai mici (cel mult `randuri_tehnic`), cele doua alegeri si nota tastelor. Inaltimea
	ferestrei urmeaza numarul de randuri (asezarea pe 1920x1080)."""
	x, y = _scara(latime, inaltime)
	fl = x(1400)
	ty, th = 25, 65
	my = ty + th + 15
	mh = randuri_mesaj * 41
	ey = my + mh + 10
	eh = max(1, randuri_tehnic) * 33 if randuri_tehnic else 1
	ly = ey + eh + 15
	lh = 2 * 56
	ny = ly + lh + 15
	nh = 45
	fh = ny + nh + 20
	return """
	<screen name="HdsPazaModelIntrebare" position="center,center" size="%(fl)d,%(fh)d" flags="wfNoBorder" backgroundColor="#00101828" title="Întrebare">
		<eLabel position="0,0" size="%(fl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="tehnic" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="alegeri" position="%(mx)d,%(ly)d" size="%(ll)d,%(lh)d" font="Regular;%(lf)d" itemHeight="%(ih)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" foregroundColorSelected="#00101828" backgroundColorSelected="#00f5b83d" transparent="0" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(ef)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"fl": fl, "fh": y(fh), "linie": max(2, y(4)), "mx": x(50), "cl": fl - 2 * x(50),
		"ty": y(ty), "th": y(th), "tf": y(44),
		"my": y(my), "mh": y(mh), "mf": y(30),
		"ey": y(ey), "eh": max(1, y(eh)), "ef": y(24),
		"ly": y(ly), "lh": y(lh), "ll": x(600), "lf": y(32), "ih": y(56),
		"ny": y(ny), "nh": y(nh),
	}


class HdsPazaModelRefuz(Screen):
	"""text: refuzul pazei pentru un pachet (Components.HdsPazaModel.textRefuz); OK sau EXIT inchide."""

	def __init__(self, session, text, titlu=None):
		marime = getDesktop(0).size()
		self.skin = skinRefuz(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = titlu or _("Pachetul nu se scrie")
		mesaj, tehnic = texteRefuz(text)
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["mesaj"] = StaticText(mesaj)
		self["tehnic"] = StaticText(tehnic)
		self["nota"] = StaticText(_("OK sau EXIT închide fereastra."))
		self["actiuni"] = ActionMap(["OkCancelActions"], {
			"ok": self.close,
			"cancel": self.close,
		}, -1)


class HdsPazaModelIntrebare(Screen):
	"""O intrebare cu doua alegeri; close(True) pentru prima („Da ...”), close(False) pentru „Nu” sau EXIT.
	text: textul simplu, apoi, dupa un rand gol, randurile tehnice (ca la texteRefuz). implicit_da: alegerea de la
	deschidere."""

	def __init__(self, session, text, titlu, da=None, nu=None, implicit_da=False, randuri_mesaj=9, randuri_tehnic=6):
		marime = getDesktop(0).size()
		self.skin = skinIntrebare(marime.width(), marime.height(), randuri_mesaj, randuri_tehnic)
		Screen.__init__(self, session)
		mesaj, tehnic = texteRefuz(text)
		self.setTitle(titlu)
		self._implicit = 0 if implicit_da else 1
		self["titlu"] = StaticText(titlu)
		self["mesaj"] = StaticText(mesaj)
		self["tehnic"] = StaticText(tehnic)
		self["alegeri"] = MenuList([da or _("Da"), nu or _("Nu")])
		self["nota"] = StaticText(_("Săgețile sus și jos aleg, OK confirmă, EXIT înseamnă „Nu”."))
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self._ok,
			"cancel": self._nu,
			"up": self._sus,
			"down": self._jos,
		}, -1)
		self.onLayoutFinish.append(self._laInceput)

	def _laInceput(self):
		self["alegeri"].moveToIndex(self._implicit)

	def _sus(self):
		self["alegeri"].up()

	def _jos(self):
		self["alegeri"].down()

	def _ok(self):
		self.close(self["alegeri"].getSelectionIndex() == 0)

	def _nu(self):
		self.close(False)


class HdsPazaModel(Screen):
	"""Diagnosticul pornirii. verdict: dict-ul lui Components.HdsPazaModel.verdict(); fara el se citeste acum.
	din_meniu=False: ecranul pornirii (nu se inchide); True: deschis din meniu (OK si EXIT il inchid)."""

	# standby opreste canalul (nu ruleaza niciunul aici); mytest.py PowerKey cere atributul pentru standby si oprire
	ALLOW_SUSPEND = Screen.SUSPEND_STOPS
	DIN_MENIU = False

	def __init__(self, session, verdict=None, din_meniu=None):
		self.din_meniu = self.DIN_MENIU if din_meniu is None else bool(din_meniu)
		if verdict is None:
			from Components import HdsPazaModel
			verdict = HdsPazaModel.verdict()
		self._verdict = verdict
		adresa = adresaWeb()
		try:
			t = texte(verdict, adresa, self.din_meniu)
		except Exception as eroare:
			# ecranul trebuie sa se vada si cand diagnosticul nu merge: mesajul pazei, fara cod si fara tabel
			print("[HdsPazaModel] diagnosticul: %s" % eroare)
			t = textePazaVechi(verdict, adresa, self.din_meniu)
		self._texte = t
		marime = getDesktop(0).size()
		self.skin = skinEcran(marime.width(), marime.height(), [r["stare"] for r in t["randuri"]], bool(t["cod"]))
		Screen.__init__(self, session)
		# acelasi nume ca NUME_SKIN, scris direct (testul formelor din skin citeste numele cu ast)
		self.skinName = ["HdsDiagnosticPornireEcran"]
		self.setTitle(t["titlu"])
		self["titlu"] = StaticText(t["titlu"])
		self["software"] = StaticText(t["software"])
		self["cod_eticheta"] = StaticText(_("Cod") if t["cod"] else "")
		self["cod"] = StaticText(t["cod"])
		self["mesaj"] = StaticText(t["mesaj"])
		self["h_citit"] = StaticText(_("Citit pe receptor"))
		self["h_cerut"] = StaticText(_("Cerut de software"))
		self["h_cod"] = StaticText(_("Cod"))
		for i in range(RANDURI_MAX):
			r = t["randuri"][i] if i < len(t["randuri"]) else {}
			self["r%d_e" % i] = StaticText(r.get("eticheta", ""))
			self["r%d_g" % i] = StaticText(r.get("citit", ""))
			self["r%d_a" % i] = StaticText(r.get("cerut", ""))
			self["r%d_c" % i] = StaticText(r.get("cod", ""))
		self["rugaminte"] = StaticText(t["rugaminte"])
		self["nota"] = StaticText(t["nota"])
		self["cefaci"] = StaticText(t["cefaci"])
		self._qr_text = self._textQr(adresa)
		if CanvasSource is not None:
			self["qr"] = CanvasSource()
			self.onLayoutFinish.append(self._deseneazaQr)
		if self.din_meniu:
			self["actiuni"] = ActionMap(["OkCancelActions"], {
				"ok": self.close,
				"cancel": self.close,
			}, -1)
		else:
			# OK si EXIT sunt prinse aici ca sa nu inchida fereastra
			self["actiuni"] = ActionMap(["OkCancelActions"], {
				"ok": self.nimic,
				"cancel": self.nimic,
			}, -1)
		self._incercari = 0
		self._ceas = None
		if not adresa:
			self._ceas = eTimer()
			try:
				self._legatura = self._ceas.timeout.connect(self._cautaAdresa)
			except AttributeError:
				self._ceas.callback.append(self._cautaAdresa)
			self._ceas.start(INTERVAL_ADRESA_MS, False)
		self.onClose.append(self._laInchidere)
		if not self.din_meniu:
			print("[HdsPazaModel] pornirea nu a reusit: %s | %s" % (" ".join(t["coduri"]) or "-", " | ".join(
				"%s=%s" % (r["cheie"], r["citit"]) for r in t["randuri"])))

	def _textQr(self, adresa):
		from Components import HdsDiagnostic
		try:
			return HdsDiagnostic.textQr(adresa, self._verdict)
		except Exception as eroare:
			print("[HdsPazaModel] textul codului QR: %s" % eroare)
			return ""

	def _deseneazaQr(self):
		deseneazaQr(self, "qr", self._qr_text)

	def _cautaAdresa(self):
		self._incercari += 1
		adresa = adresaWeb()
		if adresa:
			self["nota"].setText(textNota(adresa))
			self._qr_text = self._textQr(adresa)
			self._deseneazaQr()
		if adresa or self._incercari >= INCERCARI_ADRESA:
			self._ceas.stop()

	def _laInchidere(self):
		if self._ceas is not None:
			self._ceas.stop()

	def nimic(self):
		pass


class HdsDiagnosticPornire(HdsPazaModel):
	"""Diagnosticul pornirii deschis din Meniu > Informatii despre sistem: aceleasi date, OK sau EXIT il inchid."""

	DIN_MENIU = True
