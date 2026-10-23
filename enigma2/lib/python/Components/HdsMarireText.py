# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMarireText.py: ecranele cu textul marit (Marimea textului, config.osd.fontscale 105-130 %, Screens/FontSetup.py).
#
# skin.py inmulteste fontul fiecarui element cu procentul (skin._hds_scaleaza), nu si caseta lui: un text de mai multe
# randuri care la 100 % umplea caseta isi pierde ultimele randuri, iar unul pe un singur rand iese pe lat. Ecranele care
# au loc in jur se potrivesc cu uneltele de aici, NUMAI cand textul e marit: la 100 % (si sub) totul ramane exact cum e
# in skin.
#   marit()                  - textul e marit (procentul trece de 100)?
#   inaltimeText(eticheta)   - cati pixeli ocupa textul de acum al unei eLabel, de la marginea de sus a casetei;
#   Asezare(ecran)           - dreptunghiurile din skin ale elementelor ecranului, tinute minte o data, ca orice
#                              potrivire sa porneasca de la ele (textele se schimba de la o pagina la alta);
#   Asezare.creste(...)      - o eticheta creste pana ii incape textul, iar ce e sub ea (sau deasupra) in aceeasi
#                              coloana se muta cu diferenta; ce atinge marginea zonei se strange, ca marginea sa ramana;
#   scurtatPeInaltime(...)   - textul taiat dupa ultimul cuvant care incape in inaltimea data, cu "..." la capat;
#   scurtatPeLatime(...)     - un rand taiat la ultima litera care incape in latimea casetei, cu "..." la capat
#                              (nu se mai foloseste pe ecrane: un rand care nu incape ramane intreg si deruleaza,
#                              lib/gui/elabel.h, eDerulare).
# Masurarea se face cu eticheta insasi (eLabel.calculateSize, fontul si marimea de acum). Fisierul nu importa nimic din
# enigma2 la incarcare, ca probele de pe PC sa-l poata folosi cu etichete false.

PUNCTE = "\u2026"
# un element care atinge marginea zonei (cel mult atatia pixeli departe de ea) si e mai inalt de atat se strange;
# unul mai jos (o linie de 1-2 px, chenarul de jos) ramane pe loc
LANGA_MARGINE = 16


def procent():
	"""Marimea textului aleasa (skin.getFontScalePercent), 100 fara skin (probele de pe PC)."""
	try:
		import skin
		return int(skin.getFontScalePercent())
	except Exception:
		return 100


def marit():
	return procent() > 100


# Fonturile puse din cod (gFont in Python, nu din skin): skin.py mareste numai fonturile citite din skin, deci un ecran
# care isi pune singur fontul (randuri de liste, etichete, desene pe panza) il trece prin functiile de mai jos, ca sa
# urmeze aceeasi Marime a textului. La 100 % marimile raman exact cele date.
#   marimeCod(marime)        - marimea fontului la procentul ales, cu formula din skin.py (_hds_scaleaza);
#   inaltimeCod(inaltime)    - inaltimea unui rand sau a casetei textului, crescuta cu procentul NUMAI peste 100 %
#                              (ca randurile din Components/ChoiceList.py); la 100 % si sub ramane cea data;
#   fontCod(familie, marime) - gFont-ul gata facut: familia HD Satelit si sub un skin strain (skin.fontHds), marimeCod;
#   randuriCod(lista, rand)  - dupa skin (onLayoutFinish sau applySkin): randul listei e cel socotit de cod, chiar daca
#                              skinul ii da itemHeight, si lista ramane cu randuri intregi (numai cu textul marit).

def marimeCod(marime, p=None):
	"""Marimea unui font pus din cod la Marimea textului aleasa (`p`, implicit procent()): marime * p // 100, ca
	skin._hds_scaleaza; la 100 % exact `marime`."""
	p = procent() if p is None else int(p)
	m = int(marime)
	if p == 100:
		return m
	return max(1, m * p // 100)


def inaltimeCod(inaltime, p=None):
	"""Inaltimea unui rand (sau a casetei) care tine un font pus din cod: creste odata cu fontul cand textul e marit,
	altfel literele mai mari se taie jos; la 100 % si sub ramane `inaltime`."""
	p = procent() if p is None else int(p)
	h = int(inaltime)
	if p <= 100:
		return h
	return h * p // 100


def familieCod(familie):
	"""Familia fontului: cea HD Satelit cu acelasi rol sub un skin strain (skin.fontHds), altfel cea data."""
	try:
		import skin
		return skin.fontHds(familie)
	except Exception:
		return familie


def fontCod(familie, marime, p=None):
	"""gFont pentru un text desenat din cod, cu Marimea textului ca fonturile din skin (familieCod, marimeCod)."""
	from enigma import gFont
	return gFont(familieCod(familie), marimeCod(marime, p))


def randuriCod(componenta, rand):
	"""Lista desenata din cod, dupa skin: randul de `rand` pixeli (socotit cu inaltimeCod) inlocuieste itemHeight din
	skin, iar caseta listei se scurteaza la randuri intregi. Numai cu textul marit: la 100 % si sub nu schimba nimic.
	-> True daca a schimbat ceva."""
	if not marit():
		return False
	inst = getattr(componenta, "instance", None)
	if inst is None:
		return False
	try:
		componenta.l.setItemHeight(int(rand))
	except Exception:
		try:
			inst.setItemHeight(int(rand))
		except Exception:
			return False
	randuriIntregi(inst, int(rand))
	return True


def marimeFont(eticheta, implicit=24):
	"""Marimea in pixeli a fontului unei eLabel (cu marirea aplicata)."""
	try:
		return int(eticheta.getFont().pointSize)
	except Exception:
		return implicit


def inaltimeText(eticheta):
	"""Pixelii ocupati de textul de acum al unei eLabel, de la marginea de sus a casetei pana sub ultimul rand. Cu valign
	top primul rand are linia de baza la ascendentul fontului (lib/gdi/font.cpp, cursor = area.y + ascender), iar
	calculateSize da numai dreptunghiul literelor, fara locul de deasupra lor: se adauga, socotit larg, 0,45 x marimea
	fontului (cat lasa un rand fara majuscule). 0 fara text."""
	try:
		h = int(eticheta.calculateSize().height())
	except Exception:
		return 0
	if h <= 0:
		return 0
	return h + marimeFont(eticheta) * 45 // 100 + 2


def latimeText(eticheta):
	try:
		return int(eticheta.calculateSize().width())
	except Exception:
		return 0


def _instante(ecran):
	"""(instanta, componenta) pentru toate elementele unui ecran: componentele, elementele cu sursa (renderer) si
	etichetele fixe din skin (additionalWidgets), fiecare o data."""
	vazute = set()
	rez = []

	def adauga(o):
		inst = getattr(o, "instance", None)
		if inst is None or id(inst) in vazute:
			return
		vazute.add(id(inst))
		rez.append((inst, o))
	try:
		for _k, v in list(ecran.items()):
			adauga(v)
	except Exception:
		pass
	for r in getattr(ecran, "renderer", None) or []:
		adauga(r)
	for w in getattr(ecran, "additionalWidgets", None) or []:
		adauga(w)
	return rez


def _puneScrollLabel(comp, x, y, l, h):
	"""Un ScrollLabel (Components/ScrollLabel.py) mutat si cu alta inaltime: pagina se socoteste din nou ca in
	applySkin (randuri intregi), bara de derulare la fel, iar textul se pune din nou (numarul de pagini)."""
	from enigma import ePoint, eSize, fontRenderClass
	lt = comp.long_text
	rand = int(fontRenderClass.getInstance().getLineHeight(lt.getFont()) or 30)
	comp.pageHeight = max(1, int(h) // rand) * rand
	inalt = comp.pageHeight + rand // 6
	comp.instance.move(ePoint(int(x), int(y)))
	comp.instance.resize(eSize(max(1, int(l)), inalt))
	if comp.scrollbar is not None:
		comp.scrollbar.move(ePoint(int(l) - 20, 0))
		comp.scrollbar.resize(eSize(20, inalt))
	comp.setText(comp.message)


class Asezare(object):
	"""Geometria din skin a elementelor unui ecran, citita o data (dupa applySkin, de exemplu in onLayoutFinish)."""

	def __init__(self, ecran):
		self.elemente = []
		self._dupaId = {}
		self._marimi = {}
		for inst, comp in _instante(ecran):
			try:
				p, s = inst.position(), inst.size()
				e = (inst, p.x(), p.y(), s.width(), s.height(), comp)
			except Exception:
				continue
			self.elemente.append(e)
			self._dupaId[id(inst)] = e
			if hasattr(inst, "getFont"):
				self._marimi[id(inst)] = marimeFont(inst, 0)

	def marimeSkin(self, inst):
		"""Marimea fontului unei etichete cand s-a citit asezarea (marita, din skin), inainte de orice potrivire."""
		m = self._marimi.get(id(inst))
		return m if m else marimeFont(inst)

	def dinSkin(self, inst):
		"""(x, y, latime, inaltime) din skin, sau None pentru o instanta necunoscuta."""
		e = self._dupaId.get(id(inst))
		return e[1:5] if e else None

	def cuprinde(self, inst):
		"""(x, y, latime, inaltime) din skin al celui mai mic element care il cuprinde pe `inst` (panoul lui), sau None."""
		e = self.dinSkin(inst)
		if e is None:
			return None
		x, y, l, h = e
		bun = None
		for o in self.elemente:
			if o[0] is inst:
				continue
			ox, oy, ol, oh = o[1:5]
			if ox <= x and oy <= y and ox + ol >= x + l and oy + oh >= y + h and (ol, oh) != (l, h):
				if bun is None or ol * oh < bun[2] * bun[3]:
					bun = (ox, oy, ol, oh)
		return bun

	def pune(self, inst, x, y, l, h):
		from enigma import ePoint, eSize
		e = self._dupaId.get(id(inst))
		comp = e[5] if e else None
		if comp is not None and getattr(comp, "long_text", None) is not None and hasattr(comp, "pageHeight"):
			_puneScrollLabel(comp, x, y, l, h)
			return
		inst.move(ePoint(int(x), int(y)))
		inst.resize(eSize(max(1, int(l)), max(1, int(h))))

	def refa(self):
		"""Toate elementele la locul lor din skin."""
		for e in self.elemente:
			try:
				self.pune(e[0], *e[1:5])
			except Exception:
				pass

	def creste(self, inst, nevoie, margine, sus=False, maxim=None):
		"""Eticheta `inst` creste pana la `nevoie` pixeli inaltime (in jos; cu sus=True in sus), cel mult cu `maxim`.
		Elementele din coloana ei (care se suprapun cu ea pe orizontala) aflate intre ea si `margine` (y-ul marginii
		zonei: jos, sau sus cu sus=True) se muta cu diferenta; cele care ating marginea se strang (marginea ramane pe
		loc), iar liniile subtiri de la margine raman. Pleaca mereu de la geometria din skin. -> cu cat a crescut."""
		e = self.dinSkin(inst)
		if e is None:
			return 0
		x, y, l, h = e
		d = int(nevoie) - h
		if maxim is not None:
			d = min(d, int(maxim))
		if sus:
			d = min(d, y - int(margine))
		if d <= 0:
			self.pune(inst, x, y, l, h)
			return 0
		if sus:
			self.pune(inst, x, y - d, l, h + d)
		else:
			self.pune(inst, x, y, l, h + d)
		for o in self.elemente:
			if o[0] is inst:
				continue
			ox, oy, ol, oh = o[1:5]
			if ox >= x + l or ox + ol <= x:
				continue
			if sus:
				if oy + oh > y or oy < margine:
					continue
				if oy <= margine + LANGA_MARGINE:
					if oh > LANGA_MARGINE:
						self.pune(o[0], ox, oy, ol, oh - d)
					continue
				self.pune(o[0], ox, oy - d, ol, oh)
			else:
				if oy < y + h or oy + oh > margine:
					continue
				if oy + oh >= margine - LANGA_MARGINE:
					if oh > LANGA_MARGINE:
						self.pune(o[0], ox, oy + d, ol, oh - d)
					continue
				self.pune(o[0], ox, oy + d, ol, oh)
		return d


def marimeBaza(eticheta):
	"""Marimea fontului unei eLabel la 100 % (skin._hds_scaleaza: marime * procent // 100, deci la loc rotunjit in sus)."""
	m, p = marimeFont(eticheta), procent()
	return m if p <= 100 else (m * 100 + p - 1) // p


def puneMarime(eticheta, marime):
	from enigma import gFont
	f = eticheta.getFont()
	eticheta.setFont(gFont(f.family, int(marime)))


def latimeRand(eticheta):
	"""Latimea textului de acum al unei eLabel pe un singur rand (eticheta trece pe un rand: noWrap)."""
	try:
		eticheta.setNoWrap(1)
	except Exception:
		pass
	return latimeText(eticheta)


def imparteRandul(asezare, etichete, margine=16):
	"""Tastele colorate dintr-un rand (`etichete`: [(instanta, textul ei)], de la stanga la dreapta): latimea randului (de la marginea din stanga a
	primei la cea din dreapta a ultimei, cu spatiile din skin intre ele) se imparte dupa textele de acum, fiecare pe un
	rand, cu `margine` pixeli liberi; ce ramana se da in parti egale. Cand nici asa nu incap toate, fiecare primeste
	partea ei din loc, iar textul ramane intreg si deruleaza (lib/gui/elabel.h, eDerulare). -> True daca au incaput
	intregi."""
	sk = [(e, asezare.dinSkin(e), t) for e, t in etichete]
	sk = [b for b in sk if b[1] is not None]
	if not sk:
		return True
	x0 = sk[0][1][0]
	x1 = sk[-1][1][0] + sk[-1][1][2]
	spatii = [max(0, sk[i + 1][1][0] - (sk[i][1][0] + sk[i][1][2])) for i in range(len(sk) - 1)]
	loc = x1 - x0 - sum(spatii)
	nevoi = [latimeRand(e) + margine if t else 0 for e, _g, t in sk]
	total = sum(nevoi)
	incap = total <= loc
	if incap:
		rest = (loc - total) // len(sk)
		latimi = [n + rest for n in nevoi]
	else:
		latimi = [max(1, loc * n // max(1, total)) for n in nevoi]
	x = x0
	for i, (e, (ex, ey, el, eh), t) in enumerate(sk):
		asezare.pune(e, x, ey, latimi[i], eh)
		x += latimi[i] + (spatii[i] if i < len(spatii) else 0)
	return incap


def potrivesteFont(eticheta, inaltime, marime):
	"""Fontul etichetei pus la `marime` (marimea marita, din skin), apoi cu cate un pixel mai mic pana cand textul de acum
	incape in `inaltime` pixeli, dar nu sub marimea de la 100 %: un text de mai multe randuri dintr-o caseta fara loc in
	jur ramane intreg, cat de mare se poate. Se cheama din nou dupa fiecare text nou. -> marimea pusa"""
	p = procent()
	baza = marime if p <= 100 else (marime * 100 + p - 1) // p
	m = int(marime)
	puneMarime(eticheta, m)
	while m > baza and inaltimeText(eticheta) > inaltime:
		m -= 1
		puneMarime(eticheta, m)
	return m


def potrivesteFontLatime(eticheta, text, marime, latime=None):
	"""Un rand (noWrap) cu fontul pus la `marime` (marita), apoi cu cate un pixel mai mic pana cand textul incape in
	`latime` (implicit latimea casetei), dar nu sub marimea de la 100 %; daca nici atunci nu incape, textul ramane
	intreg si deruleaza (lib/gui/elabel.h, eDerulare). Eticheta ramane cu textul pus. -> marimea pusa"""
	if latime is None:
		try:
			latime = eticheta.size().width()
		except Exception:
			return marime
	p = procent()
	baza = marime if p <= 100 else (marime * 100 + p - 1) // p
	m = int(marime)
	puneMarime(eticheta, m)
	if text is not None:
		eticheta.setText(text)
	while m > baza and latimeRand(eticheta) > latime:
		m -= 1
		puneMarime(eticheta, m)
	return m


def randuriMarite(componenta):
	"""O lista (MenuList, ConfigList) cu inaltimea randului din skin (itemHeight, pe care skin.py nu o mareste) si fontul
	marit: randul creste cu procentul, ca fontul, altfel textul randului se taie jos. Se cheama dupa asezare
	(onLayoutFinish). -> True daca a schimbat ceva (la 100 % niciodata)."""
	p = procent()
	inst = getattr(componenta, "instance", None)
	if p <= 100 or inst is None:
		return False
	try:
		h = int(dict(componenta.skinAttributes or ()).get("itemHeight", 0))
	except (TypeError, ValueError):
		return False
	if h <= 0:
		return False
	inst.setItemHeight(h * p // 100)
	randuriIntregi(inst, h * p // 100)
	return True


def randuriIntregi(inst, rand):
	"""Lista scurtata la un numar intreg de randuri de `rand` pixeli (cu randul marit, ultimul rand din caseta din skin se
	vedea taiat pe jumatate)."""
	try:
		from enigma import eSize
		s = inst.size()
		h = max(rand, s.height() // rand * rand)
		if h != s.height():
			inst.resize(eSize(s.width(), h))
	except Exception:
		pass


def potrivesteInaltimile(ecran):
	"""Etichetele transparente ale unui ecran, cu textul marit: cand caseta e mai joasa decat literele (semnele de sus, ca
	la "I" cu caciula, si cozile g, p, s cu virgula), caseta creste cat trebuie, fara ca textul sa se mute: cu valign
	center la fel in sus si in jos (cu un numar par de pixeli, deci mijlocul ramane), cu valign top in jos, cu valign
	bottom in sus. Pe un rand (noWrap) dupa marimea fontului; pe mai multe randuri dupa textul de acum: centrate cat
	dreptunghiul literelor, aliniate sus numai cand ies doar cozile ultimului rand (un rand intreg ascuns il potriveste
	ecranul lui). Fiind transparenta, numai locul in care se poate desena textul e mai mare. Se cheama la asezarea
	fiecarui ecran (Components/GUISkin.py), inainte de onLayoutFinish; la 100 % nu face nimic."""
	if not marit():
		return
	from enigma import ePoint, eSize
	vazute = set()
	obiecte = list(getattr(ecran, "additionalWidgets", None) or []) + list(getattr(ecran, "renderer", None) or [])
	try:
		obiecte += [v for _k, v in list(ecran.items())]
	except Exception:
		pass
	for o in obiecte:
		inst = getattr(o, "instance", None)
		if inst is None or id(inst) in vazute or not hasattr(inst, "calculateSize") or getattr(o, "long_text", None) is not None:
			continue
		vazute.add(id(inst))
		try:
			a = dict(o.skinAttributes or ())
		except Exception:
			continue
		if a.get("transparent", "0") in ("0", "false"):
			continue
		randuri = a.get("noWrap", "0") in ("0", "false")
		try:
			m = marimeFont(inst, 0)
			if m <= 0:
				continue
			p, s = inst.position(), inst.size()
			va = a.get("valign", "top")
			if randuri:
				th = int(inst.calculateSize().height())
				if th <= 0 or va == "bottom":
					continue
				nevoie = th + 2 if va == "center" else inaltimeText(inst)
				if va != "center" and nevoie - s.height() > m * 80 // 100:
					continue
			elif va == "center":
				nevoie = m * 120 // 100 + 2
			else:
				nevoie = m * 140 // 100 + 1
			d = nevoie - s.height()
			if d <= 0:
				continue
			# locul din skin, pentru cine potriveste mai departe (de exemplu randurile din benzi ale paginii tehnice)
			try:
				o.hdsLocSkin = (p.x(), p.y(), s.width(), s.height())
			except Exception:
				pass
			if va == "center":
				d += d % 2
				inst.move(ePoint(p.x(), p.y() - d // 2))
			elif va == "bottom":
				inst.move(ePoint(p.x(), p.y() - d))
			inst.resize(eSize(s.width(), s.height() + d))
		except Exception:
			pass


def locPentruCozi(eticheta, maxim):
	"""O eticheta aliniata sus, al carei text se schimba des (ajutorul randului ales, o nota), cu textul marit: caseta
	creste in jos cu locul cozilor ultimului rand (0,45 x marimea fontului), cel mult `maxim` pixeli (cat e liber sub
	ea); textul nu se muta. -> cu cat a crescut (0 la 100 %)."""
	if not marit() or eticheta is None:
		return 0
	try:
		from enigma import eSize
		s = eticheta.size()
		d = min(int(maxim), marimeFont(eticheta) * 45 // 100)
		if d > 0:
			eticheta.resize(eSize(s.width(), s.height() + d))
		return max(0, d)
	except Exception:
		return 0


def potrivesteEticheteleFixe(ecran):
	"""Etichetele cu text fix ale skinului (eLabel text="..." pe un rand, noWrap, aliniate la stanga), cu textul marit:
	fontul ramane la marimea aleasa; cand textul iese din caseta (sigla "HD SATELIT" din capul ferestrelor Pro la
	125-130 %, legenda "Inchide" a barei Pro, eticheta "HbbTV" a barei Clasic), caseta creste spre dreapta cat ii
	trebuie, dar numai pana la primul element din acelasi rand (vecinul ramane pe loc). Ce tot nu incape deruleaza
	(lib/gui/elabel.h, eDerulare). Se cheama la asezarea fiecarui ecran (Components/GUISkin.py); la 100 % nu face
	nimic."""
	if not marit():
		return
	toate = None
	for w in getattr(ecran, "additionalWidgets", None) or []:
		inst = getattr(w, "instance", None)
		if inst is None or not hasattr(inst, "calculateSize"):
			continue
		try:
			a = dict(w.skinAttributes or ())
		except Exception:
			continue
		if not a.get("text") or a.get("noWrap", "0") in ("0", "false") or a.get("halign", "left") != "left":
			continue
		try:
			p, s = inst.position(), inst.size()
			x, y, l, h = p.x(), p.y(), s.width(), s.height()
			nevoie = latimeText(inst)
			if l <= 2 or nevoie <= l:
				continue
			if toate is None:
				toate = _instante(ecran)
			limita = x + nevoie
			try:
				limita = min(limita, ecran.instance.size().width())
			except Exception:
				pass
			for i2, _o in toate:
				if i2 is inst:
					continue
				p2, s2 = i2.position(), i2.size()
				if s2.width() <= 0 or p2.y() >= y + h or p2.y() + s2.height() <= y or p2.x() < x + l:
					continue
				limita = min(limita, p2.x())
			if limita > x + l:
				from enigma import eSize
				inst.resize(eSize(limita - x, h))
		except Exception:
			pass


def potrivesteStiva(asezare, blocuri, jos, micsorabile=()):
	"""Elementele din `blocuri`, de sus in jos in aceeasi coloana, puse unul sub altul: [(instanta, nevoie)], unde
	nevoie() da inaltimea ceruta de textul de acum (None = cea din skin); fiecare are cel putin inaltimea din skin, iar
	distantele dintre ele raman cele din skin. Cand ultimul ar trece de `jos`, intai casetele cu text mai scurt decat
	locul lor din skin se strang la cat le cere textul, apoi fontul etichetelor din `micsorabile` scade cu cate un pixel
	(niciuna sub marimea de la 100 %), pana cand totul incape: textul ramane intreg, cat de mare se poate.
	-> True daca a incaput."""
	sk = [(inst, nevoie, asezare.dinSkin(inst)) for inst, nevoie in blocuri]
	sk = [b for b in sk if b[2] is not None]
	if not sk:
		return True
	p = procent()
	baze = {}
	for e in micsorabile:
		m = asezare.marimeSkin(e)
		puneMarime(e, m)
		baze[id(e)] = m if p <= 100 else (m * 100 + p - 1) // p
	def socoteste(strange):
		inaltimi = []
		for inst, nevoie, (x, y, l, h) in sk:
			n = nevoie() if nevoie else None
			if n:
				inaltimi.append(int(n) if strange else max(h, int(n)))
			else:
				inaltimi.append(h)
		capat = sk[0][2][1]
		for i, (inst, nevoie, (x, y, l, h)) in enumerate(sk):
			if i:
				capat += max(0, y - (sk[i - 1][2][1] + sk[i - 1][2][3]))
			capat += inaltimi[i]
		return inaltimi, capat
	while True:
		inaltimi, capat = socoteste(False)
		if capat <= jos:
			break
		inaltimi, capat = socoteste(True)
		if capat <= jos:
			break
		mai = [e for e in micsorabile if marimeFont(e) > baze[id(e)]]
		if not mai:
			break
		for e in mai:
			puneMarime(e, marimeFont(e) - 1)
	cur = sk[0][2][1]
	for i, (inst, nevoie, (x, y, l, h)) in enumerate(sk):
		if i:
			cur += max(0, y - (sk[i - 1][2][1] + sk[i - 1][2][3]))
		asezare.pune(inst, x, cur, l, inaltimi[i])
		cur += inaltimi[i]
	return cur <= jos


def scurtatPeInaltime(eticheta, text, inaltime):
	"""Textul care incape in `inaltime` pixeli ai etichetei (masurat cu ea): intreg, sau taiat dupa ultimul cuvant care
	incape, cu "..." la capat. Eticheta ramane cu textul intors."""
	def incape(t):
		eticheta.setText(t)
		return inaltimeText(eticheta) <= inaltime
	if not text or incape(text):
		return text
	locuri = [i for i, c in enumerate(text) if c in " \n"]
	jos, sus, bun = 0, len(locuri) - 1, None
	while jos <= sus:
		mijloc = (jos + sus) // 2
		t = text[:locuri[mijloc]].rstrip(" ,;:-(\n") + PUNCTE
		if incape(t):
			bun = t
			jos = mijloc + 1
		else:
			sus = mijloc - 1
	rez = bun or PUNCTE
	eticheta.setText(rez)
	return rez


def scurtatPeLatime(eticheta, text, latime=None):
	"""Un rand (eticheta cu noWrap) care incape in `latime` pixeli (implicit latimea casetei): intreg, sau taiat la
	ultima litera care incape, cu "..." la capat. Eticheta ramane cu textul intors."""
	if latime is None:
		try:
			latime = eticheta.size().width()
		except Exception:
			return text
	eticheta.setText(text or "")
	if not text or latimeText(eticheta) <= latime:
		return text
	jos, sus, bun = 0, len(text) - 1, None
	while jos <= sus:
		mijloc = (jos + sus) // 2
		t = text[:mijloc].rstrip(" ,;:-(\u2013") + PUNCTE
		eticheta.setText(t)
		if latimeText(eticheta) <= latime:
			bun = t
			jos = mijloc + 1
		else:
			sus = mijloc - 1
	rez = bun or PUNCTE
	eticheta.setText(rez)
	return rez
