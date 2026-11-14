# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTemaStergere.py: stergerea unei teme din lista de unde se alege (Aspectul ecranelor: Plugins/SystemPlugins/SkinSelector,
# tasta rosie; pagina web /skin, butonul Sterge). Aceeasi hotarare pe televizor si in web: plan() / planuri().
#
# - Tema imaginii (HDSatelit, skin_default, orice dosar tinut de un pachet al imaginii sau de pachetele protejate) nu se
#   sterge niciodata: e si tema pe care trece receptorul cand se sterge tema de pe ecran.
# - Tema dintr-un pachet enigma2-plugin-skins-*: opkg remove, prin acelasi drum ca in Extensii
#   (HdsExtensiiLucru.planStergere si Lucrare: confirmarea, progresul, fisierele imaginii puse la loc de HdsTemeSuprascrise).
#   Daca alt pachet instalat depinde de ea, nu se sterge (se spune care).
# - Tema copiata de mana (dosar cu skin.xml sub ${datadir}/enigma2, fara pachet): se sterge numai dosarul ei. O legatura
#   simbolica se scoate ea singura, fara sa se intre in ce arata.
# - Tema de pe ecran (sau aleasa pentru pornirea urmatoare): programeaza() alege tema HD Satelit (sau tema aleasa deja, daca
#   e alta), tine minte tema in STARE, apoi interfata se reporneste; la pornire (laPornire, din extensia SkinSelector)
#   tema se sterge si omul afla rezultatul. Incercarile se numara: dupa INCERCARI_MAX porniri intrerupte se renunta.
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau radacina si config).

import os
import shutil
import stat

STARE = "/etc/enigma2/hds-tema-de-sters"
INCERCARI_MAX = 2
# pachetele care tin tema imaginii, si cand manifestul imaginii nu se poate citi (aceleasi pe care Ipkg nu le sterge)
try:
	from Components.Ipkg import PROTECTED_REMOVE as PROTEJATE
except ImportError:
	try:   # probele de pe PC: modulul din acelasi dosar
		from Ipkg import PROTECTED_REMOVE as PROTEJATE
	except ImportError:   # Ipkg cere enigma: aceeasi lista
		PROTEJATE = frozenset(("hdsatelit-skin", "enigma2", "enigma2-hdsatelit"))
FEL_PACHET = "pachet"
FEL_DOSAR = "dosar"
FEL_LEGATURA = "legatura"
FEL_INCOMPLETA = "incompleta"   # dosarul ramas al unei teme sterse pe jumatate (fara skin.xml): incomplete()


def _vecin(nume):
	try:
		return __import__("Components." + nume, fromlist=[nume])
	except ImportError:   # probele de pe PC: modulele din acelasi dosar
		return __import__(nume)


def _S():
	return _vecin("HdsSkinuri")


def _P():
	return _vecin("HdsPachete")


def _TS():
	return _vecin("HdsTemeSuprascrise")


def _L():
	return _vecin("HdsExtensiiLucru")


def N_(text):
	return text


def _t(text, traducere=None):
	if traducere is not None:
		try:
			return traducere(text)
		except Exception:
			return text
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsTemaStergere] %s" % text)


def _caleReceptor(cale, radacina):
	"""calea de pe receptor (ca in listele opkg) a unei cai de sub `radacina` (probele de pe PC dau alta radacina)"""
	if not radacina or radacina == "/":
		return cale
	rel = os.path.relpath(cale, radacina).replace("\\", "/")
	return "/" + rel.lstrip("/")


def numeBun(nume):
	"""numele unui dosar de tema chiar sub radacina: fara bare, fara .., fara inceput cu punct, nu skin_default"""
	if not isinstance(nume, str) or not nume or "\0" in nume:
		return False
	if "/" in nume or "\\" in nume or nume in (".", "..") or nume.startswith(".") or nume.startswith("skin_default"):
		return False
	return True


def _pacheteImagine(radacina):
	try:
		I = _vecin("HdsPluginuriImagine")
		return set(I.pacheteImagine("" if radacina == "/" else radacina))
	except Exception as eroare:
		_jurnal("manifestul imaginii: %s" % eroare)
		return set()


def _dependenti(radacina):
	"""{pachet: [pachetele instalate care il cer in Depends]} din starea opkg (Depends-ul instalat, nu cel din liste).
	O alternativa (a | b) nu se numara: opkg o lasa sa treaca daca ramane cealalta."""
	P = _P()
	try:
		conf = P.citeste_configurarea(radacina)
		strofe = P.citeste_strofe(P._cale(radacina, conf.status_file))
	except Exception as eroare:
		_jurnal("starea pachetelor: %s" % eroare)
		return {}
	rez = {}
	for s in strofe:
		st = s.get("status", "").split()
		if "installed" not in st or "not-installed" in st:
			continue
		n = s.get("package", "")
		for parte in s.get("depends", "").split(","):
			if "|" in parte:
				continue
			d = parte.strip().split(" ", 1)[0].split("(", 1)[0].strip()
			if d and d != n:
				rez.setdefault(d, []).append(n)
	return rez


def _marimeDosar(dosar):
	"""octetii fisierelor obisnuite din dosar, fara sa urmeze legaturi"""
	total = 0
	for baza, dosare, fisiere in os.walk(dosar, followlinks=False):
		for f in fisiere:
			try:
				s = os.lstat(os.path.join(baza, f))
			except OSError:
				continue
			if stat.S_ISREG(s.st_mode):
				total += s.st_size
	return total


def _marimePachet(pachet, radacina):
	P = _P()
	try:
		dosar_info = P._cale(radacina, P.citeste_configurarea(radacina).info_dir)
	except Exception:
		dosar_info = P._cale(radacina, P.DOSAR_INFO)
	total = 0
	for r in P._randuri(os.path.join(dosar_info, pachet + ".list")):
		try:
			s = os.lstat(P._cale(radacina, r.split("\t", 1)[0].strip()))
		except (OSError, ValueError):
			continue
		if stat.S_ISREG(s.st_mode):
			total += s.st_size
	return total


# ------------------------------------------------------------------ temele incomplete (HDSatelit 0.7.5, TMR)
# O tema stearsa pe jumatate de mana (Satedu t=32518, JAKITAKI: golita prin FTP, care nu sterge dosarele) lasa sub
# ${datadir}/enigma2 un dosar fara skin.xml: nu e in lista temelor (HdsSkinuri.lista cere skin.xml) si nu se putea sterge din
# meniu. incomplete() o arata separat, cu semnul „incompletă”, numai pentru stergere (nu se poate alege). Un dosar e tema
# incompleta numai daca: e chiar sub radacina, nu e legatura, nu are skin.xml, nu e nimic montat in el sau sub el, nu are
# nume de sigle (picon), nu tine niciun pachet instalat nicio cale din el (dosarele imaginii si ale pluginurilor raman
# neatinse), si arata a tema: gol (numai dosare goale si fisiere ascunse), prev.png, sau un .xml care incepe cu <skin.
SEMNE_INCEPUT = 4096
CITITE_MAX = 3000   # intrari citite cel mult dintr-un dosar (sa nu se piarda timp intr-un dosar mare de date)


def _montariSub(dosar):
	"""punctele de montare din dosar sau de sub el (din /proc/mounts); [] pe PC"""
	baza = os.path.realpath(dosar).rstrip("/") + "/"
	rez = []
	try:
		with open("/proc/mounts") as f:
			for rand in f:
				p = rand.split()
				if len(p) > 1:
					m = p[1].replace("\\040", " ").rstrip("/") + "/"
					if m.startswith(baza):
						rez.append(p[1])
	except (IOError, OSError):
		pass
	return rez


def _aratATema(dosar):
	"""dosarul ramas arata a tema: gol (numai dosare si fisiere ascunse), prev.png sau un .xml de tema (<skin)"""
	if os.path.isfile(os.path.join(dosar, "prev.png")):
		return True
	citite = 0
	gol = True
	for baza, dosare, fisiere in os.walk(dosar, followlinks=False):
		for f in fisiere:
			citite += 1
			if citite > CITITE_MAX:
				return False
			if f.startswith("."):
				continue
			gol = False
			if f.lower().endswith(".xml") and baza.count(os.sep) - dosar.count(os.sep) <= 2:
				try:
					with open(os.path.join(baza, f), "rb") as g:
						if b"<skin" in g.read(SEMNE_INCEPUT):
							return True
				except (IOError, OSError):
					pass
		citite += len(dosare)
		if citite > CITITE_MAX:
			return False
	return gol


def _cuPachet(nume_lista, root, radacina):
	"""numele dosarelor din care un pachet instalat tine macar o cale (dosarul insusi sau ceva de sub el)"""
	baza = _caleReceptor(root, radacina).rstrip("/") + "/"
	cautate = set(nume_lista)
	rez = set()
	P = _P()
	try:
		dosar_info = P._cale(radacina, P.citeste_configurarea(radacina).info_dir)
	except Exception:
		dosar_info = P._cale(radacina, P.DOSAR_INFO)
	try:
		liste = [n for n in os.listdir(dosar_info) if n.endswith(".list")]
	except OSError:
		return rez
	for n in liste:
		for r in P._randuri(os.path.join(dosar_info, n)):
			c = r.split("\t", 1)[0].strip()
			if c.startswith(baza):
				primul = c[len(baza):].split("/", 1)[0]
				if primul in cautate:
					rez.add(primul)
	return rez


def _candidata(nume, root):
	"""verificarile de pe disc ale unei teme incomplete (fara listele opkg)"""
	S = _S()
	if not numeBun(nume) or nume in (S.DOSAR_IMAGINE, S.IMPLICIT) or "picon" in nume.casefold():
		return False
	dosar = os.path.join(root, nume)
	if os.path.islink(dosar) or not os.path.isdir(dosar) or os.path.exists(os.path.join(dosar, "skin.xml")):
		return False
	if os.path.realpath(os.path.dirname(os.path.realpath(dosar))) != os.path.realpath(root):
		return False
	if _montariSub(dosar):
		return False
	return _aratATema(dosar)


def incomplete(root=None, radacina="/"):
	"""numele temelor incomplete de sub radacina (vezi mai sus), in ordinea alfabetica"""
	if root is None:
		root = _S().radacina()
	try:
		nume = os.listdir(root)
	except OSError:
		return []
	cand = [n for n in nume if _candidata(n, root)]
	if not cand:
		return []
	tinute = _cuPachet(cand, root, radacina)
	return sorted((n for n in cand if n not in tinute), key=lambda x: x.lower())


def esteIncompleta(nume, root=None, radacina="/"):
	if root is None:
		root = _S().radacina()
	return _candidata(nume, root) and nume not in _cuPachet([nume], root, radacina)


def etichetaIncompleta(nume, traducere=None):
	"""randul din lista temelor pentru o tema incompleta"""
	return "%s (%s)" % (nume, _t("incompletă", traducere))


def titluTema(nume):
	S = _S()
	return "HD Satelit" if nume == S.DOSAR_IMAGINE else nume


def planuri(nume_lista, root=None, radacina="/", activa=None, aleasa=None, traducere=None):
	"""{nume: plan} pentru temele din lista (o singura citire a listelor opkg si a starii). `activa`: dosarul temei de pe
	ecran; `aleasa`: dosarul temei alese pentru pornirea urmatoare. Planul: poate, motiv (de ce nu), fel (pachet, dosar,
	legatura), pachet, activa (pe ecran sau aleasa), pe_ecran, urmatoarea (tema pe care trece receptorul cand tema e pe ecran), elibereaza (octeti),
	dependenti, intrebare, detalii."""
	S = _S()
	if root is None:
		root = S.radacina()
	rez = {}
	cai = {}
	for nume in nume_lista:
		if numeBun(nume):
			cai[nume] = _caleReceptor(os.path.join(root, nume, "skin.xml"), radacina)
	try:
		prop = _TS().proprietari(cai.values(), radacina) if cai else {}
	except Exception as eroare:
		_jurnal("proprietarii temelor: %s" % eroare)
		prop = {}
	imagine = None
	dependenti = None
	# temele incomplete: verificarile de pe disc, apoi listele opkg citite o singura data pentru toate
	incomplete_aici = set(n for n in nume_lista if n not in cai or not os.path.isfile(os.path.join(root, n, "skin.xml")))
	incomplete_aici = set(n for n in incomplete_aici if _candidata(n, root))
	if incomplete_aici:
		incomplete_aici -= _cuPachet(incomplete_aici, root, radacina)
	for nume in nume_lista:
		p = {"nume": nume, "poate": False, "motiv": "", "fel": None, "pachet": "", "activa": False, "pe_ecran": False,
			"urmatoarea": "", "elibereaza": 0, "dependenti": [], "intrebare": "", "detalii": []}
		rez[nume] = p
		if nume in (S.DOSAR_IMAGINE, S.IMPLICIT) or not numeBun(nume):
			p["motiv"] = _t("Tema HD Satelit e tema imaginii și nu se șterge.", traducere) if nume == S.DOSAR_IMAGINE \
				else _t("Tema aceasta nu se poate șterge.", traducere)
			continue
		dosar = os.path.join(root, nume)
		if os.path.islink(dosar):
			p["fel"] = FEL_LEGATURA
		elif os.path.isdir(dosar) and os.path.isfile(os.path.join(dosar, "skin.xml")):
			p["fel"] = FEL_DOSAR
		elif nume in incomplete_aici:
			p["fel"] = FEL_INCOMPLETA
		else:
			p["motiv"] = _t("Tema nu mai este pe receptor.", traducere)
			continue
		proprietar = [x[0] for x in prop.get(cai.get(nume), [])]
		if proprietar and p["fel"] == FEL_DOSAR:
			if imagine is None:
				imagine = _pacheteImagine(radacina) | PROTEJATE
			din_imagine = [x for x in proprietar if x in imagine]
			if din_imagine:
				p["motiv"] = _t("Tema %s vine cu imaginea și nu se șterge.", traducere) % nume
				continue
			teme = [x for x in proprietar if _TS().eTema(x)]
			if not teme:
				p["motiv"] = _t("Tema %s face parte din pachetul %s. Îl poți șterge din Meniu > Pluginuri și aplicații.",
					traducere) % (nume, proprietar[0])
				continue
			p["fel"] = FEL_PACHET
			p["pachet"] = teme[0]
			if dependenti is None:
				dependenti = _dependenti(radacina)
			dep = sorted(set(dependenti.get(teme[0], [])))
			if dep:
				p["dependenti"] = dep
				p["motiv"] = _t("Tema %s nu se poate șterge: de ea depinde %s.", traducere) % (nume, ", ".join(dep[:3]))
				continue
			p["elibereaza"] = _marimePachet(teme[0], radacina)
		elif p["fel"] in (FEL_DOSAR, FEL_INCOMPLETA):
			p["elibereaza"] = _marimeDosar(dosar)
		p["poate"] = True
		p["activa"] = nume in (activa, aleasa)
		# pe ecran acum: se sterge numai dupa repornirea interfetei cu alta tema (programeaza, laPornire)
		p["pe_ecran"] = nume == activa
		if p["activa"]:
			alta = aleasa if aleasa and aleasa != nume and S.caleSkin(root, aleasa) else S.DOSAR_IMAGINE
			p["urmatoarea"] = alta
			if p["pe_ecran"]:
				p["intrebare"] = _t("Tema %s e folosită acum. Receptorul trece pe tema %s, repornește interfața și apoi "
					"șterge tema %s.", traducere) % (nume, titluTema(alta), nume)
			else:
				p["intrebare"] = _t("Ștergi tema %s? E aleasă pentru pornirea următoare; în locul ei rămâne tema %s.",
					traducere) % (nume, titluTema(alta))
		elif p["fel"] == FEL_INCOMPLETA:
			p["intrebare"] = _t("Ștergi ce a rămas din tema %s?", traducere) % nume
		else:
			p["intrebare"] = _t("Ștergi tema %s?", traducere) % nume
		if p["fel"] == FEL_PACHET:
			p["detalii"].append(_t("De unde: pachetul %s", traducere) % p["pachet"])
		elif p["fel"] == FEL_INCOMPLETA:
			p["detalii"].append(_t("Tema e incompletă: lipsește skin.xml, deci nu se mai poate folosi; se șterge dosarul ei.",
				traducere))
		elif p["fel"] == FEL_LEGATURA:
			p["detalii"].append(_t("De unde: legătură spre alt dosar; se scoate numai legătura", traducere))
		else:
			p["detalii"].append(_t("De unde: copiată de mână, fără pachet", traducere))
		marime = _P().marime_text(p["elibereaza"])
		if marime:
			p["detalii"].append(_t("Eliberează: %s", traducere) % marime)
	return rez


def plan(nume, root=None, radacina="/", activa=None, aleasa=None, traducere=None):
	return planuri([nume], root, radacina, activa, aleasa, traducere)[nume]


def planCurent(nume, config=None, root=None, traducere=None):
	"""plan() cu tema de pe ecran si cea aleasa citite acum (firul enigma2)"""
	S = _S()
	return plan(nume, root, "/", S.numeDinValoare(S.skinPornit()) or S.DOSAR_IMAGINE, S.curent(config), traducere)


# ------------------------------------------------------------------ stergerea

def _lasaAlegerea(nume, config=None, urmatoarea=None):
	"""tema de sters nu mai ramane aleasa: trece pe `urmatoarea` (HDSatelit implicit); refuzul tinut minte pentru ea se sterge"""
	S = _S()
	c = S._config(config)
	if S.curent(c) == nume:
		c.skin.primary_skin.value = S.fisier(urmatoarea or S.DOSAR_IMAGINE)
		c.skin.primary_skin.save()
		try:
			from Components.config import configfile
			configfile.save()
		except ImportError:
			pass
	r = S.refuzDeSpus()
	if r and S.numeDinValoare(r.get("skin")) == nume:
		S.stergeRefuz()


def stergeDosar(nume, root=None, traducere=None, incompleta=False, radacina="/"):
	"""(bun, mesaj): numai dosarul temei (sau numai legatura), dupa ce numele a trecut verificarea; nimic din afara lui.
	`incompleta`: dosarul ramas fara skin.xml, numai daca e inca tema incompleta (esteIncompleta: fara pachet, fara montari)"""
	S = _S()
	if root is None:
		root = S.radacina()
	if not numeBun(nume) or nume == S.DOSAR_IMAGINE:
		return False, _t("Tema aceasta nu se poate șterge.", traducere)
	dosar = os.path.join(root, nume)
	try:
		if os.path.islink(dosar):
			os.unlink(dosar)
		else:
			baza = os.path.realpath(root)
			if os.path.dirname(os.path.realpath(dosar)) != baza:
				return False, _t("Tema nu mai este pe receptor.", traducere)
			if os.path.isfile(os.path.join(dosar, "skin.xml")):
				pass
			elif not incompleta or not esteIncompleta(nume, root, radacina):
				return False, _t("Tema nu mai este pe receptor.", traducere)
			if _montariSub(dosar):
				# un disc montat in dosarul temei nu se sterge odata cu ea
				return False, _t("Tema %s nu s-a șters: în dosarul ei e montat un disc.", traducere) % nume
			shutil.rmtree(dosar)
	except OSError as eroare:
		_jurnal("%s: %s" % (dosar, eroare))
		return False, _t("Tema %s nu s-a șters: %s", traducere) % (nume, eroare.strerror or eroare)
	_jurnal("sters dosarul %s" % dosar)
	return True, _t("Tema %s a fost ștearsă.", traducere) % nume


def planPachet(p, catalog=None, argumente=None, traducere=None):
	"""(planul Extensiilor pentru opkg remove, None) sau (None, (mesaj, culoare)); titlul spune ca e o tema"""
	L = _L()
	if catalog is None:
		catalog = L.catalogLaZi() or L.incarcaCatalog()
	pachet = catalog._toate.get(p["pachet"])
	if pachet is None or not pachet.se_poate_sterge:
		return None, (_t("Tema nu mai este pe receptor.", traducere), "rau")
	rez, eroare = L.planStergere(catalog, pachet, argumente)
	if rez is None:
		return None, eroare
	rez["titlu"] = _t("Ștergi tema %s?", traducere) % p["nume"]
	rez["nume"] = p["nume"]
	# tema care nu e pe ecran nu cere repornirea interfetei
	rez["repornire"] = False
	if p.get("activa"):
		# aleasa pentru pornirea urmatoare: confirmarea Extensiilor spune si ce tema ramane
		rez["nota"] = (_t("E aleasă pentru pornirea următoare; în locul ei rămâne tema %s.", traducere) %
			titluTema(p.get("urmatoarea") or _S().DOSAR_IMAGINE) + " " + (rez.get("nota") or "")).strip()
	rez["tema"] = p["nume"]
	return rez, None


def stergeDosarAles(p, config=None, root=None, traducere=None, radacina="/"):
	"""Tema copiata de mana (sau legatura), care nu e pe ecran: daca e aleasa pentru pornirea urmatoare, alegerea trece
	intai pe tema urmatoare, apoi se sterge dosarul. (bun, mesaj)"""
	if p.get("activa"):
		_lasaAlegerea(p["nume"], config, p.get("urmatoarea"))
	return stergeDosar(p["nume"], root, traducere, p.get("fel") == FEL_INCOMPLETA, radacina)


def maiEste(nume, root, fel=None):
	"""tema e inca in lista: legatura ei sau skin.xml din dosar (opkg poate lasa dosarul cu fisierele facute de tema);
	tema incompleta: dosarul ei"""
	dosar = os.path.join(root, nume)
	if fel == FEL_INCOMPLETA:
		return os.path.islink(dosar) or os.path.isdir(dosar)
	return os.path.islink(dosar) or os.path.isfile(os.path.join(dosar, "skin.xml"))


def dupaPachet(nume, config=None, root=None):
	"""Dupa lucrarea opkg a unei teme: daca dosarul ei nu mai e, alegerea nu mai ramane pe ea. True daca s-a sters."""
	S = _S()
	if root is None:
		root = S.radacina()
	if maiEste(nume, root):
		return False
	_lasaAlegerea(nume, config)
	return True


def programeaza(p, config=None, cale=None):
	"""Tema de pe ecran: alegerea trece pe tema urmatoare, apoi tema se tine minte pentru pornire (in ordinea asta: o
	oprire intre cele doua lasa tema nestearsa, nu receptorul pe o tema care lipseste). True daca s-a scris."""
	_lasaAlegerea(p["nume"], config, p.get("urmatoarea"))
	S = _S()
	ok = S._scrieJson(cale or STARE, {"nume": p["nume"], "fel": p["fel"], "pachet": p.get("pachet", ""), "incercari": 0})
	_jurnal("tema %s se sterge la pornirea urmatoare (%s)" % (p["nume"], ok))
	return ok


def deSters(cale=None):
	d = _S()._citesteJson(cale or STARE)
	return d if d and numeBun(d.get("nume")) else None


def _uita(cale=None):
	_S()._sterge(cale or STARE)


def anuntaPeTv(text, eroare=False):
	from Screens.MessageBox import MessageBox
	from Tools import Notifications
	Notifications.AddPopup(text, MessageBox.TYPE_ERROR if eroare else MessageBox.TYPE_INFO, 0 if eroare else 20,
		"hds_tema_stearsa")


def laPornire(anunta=None, root=None, radacina="/", cale=None, pornit=None, traducere=None, porneste=None):
	"""Extensia SkinSelector, la pornirea sesiunii: tema tinuta minte se sterge acum, cu tema imaginii pe ecran.
	`pornit`: dosarul temei de pe ecran (implicit skin.py); `porneste(plan, gata)`: lucrarea opkg (implicit Lucrare).
	Intoarce ce s-a facut: None, "anulat", "dosar", "pachet", "renuntat", "ocupat"."""
	S = _S()
	cale = cale or STARE
	d = deSters(cale)
	if d is None:
		if os.path.exists(cale):
			_uita(cale)
		return None
	anunta = anunta or anuntaPeTv
	nume = d["nume"]
	if pornit is None:
		pornit = S.numeDinValoare(S.skinPornit()) or S.DOSAR_IMAGINE
	if pornit == nume:
		# tema a fost aleasa din nou inainte de repornire: stergerea nu mai e ceruta
		_jurnal("tema %s e iar pe ecran: nu se mai sterge" % nume)
		_uita(cale)
		return "anulat"
	if root is None:
		root = S.radacina()
	if not maiEste(nume, root, d.get("fel")):
		_uita(cale)
		anunta(_t("Tema %s a fost ștearsă.", traducere) % nume)
		return "dosar"
	incercari = int(d.get("incercari") or 0) + 1
	if incercari > INCERCARI_MAX:
		_uita(cale)
		anunta(_t("Tema %s nu s-a putut șterge la pornire. Încearcă din nou din Aspectul ecranelor.", traducere) % nume, True)
		return "renuntat"
	d["incercari"] = incercari
	S._scrieJson(cale, d)
	p = plan(nume, root, radacina, pornit, None, traducere)
	if not p["poate"]:
		_uita(cale)
		anunta(_t("Tema %s nu s-a șters: %s", traducere) % (nume, p["motiv"]), True)
		return "renuntat"
	if p["fel"] != FEL_PACHET:
		bun, mesaj = stergeDosar(nume, root, traducere, p["fel"] == FEL_INCOMPLETA, radacina)
		_uita(cale)
		anunta(mesaj, not bun)
		return "dosar"
	L = _L()
	motiv = L.motivOcupat(None)
	if motiv is not None:
		_jurnal("opkg ocupat la pornire: tema %s ramane de sters (%s)" % (nume, motiv[0]))
		return "ocupat"
	pl, eroare = planPachet(p, traducere=traducere)
	if pl is None:
		_uita(cale)
		anunta(_t("Tema %s nu s-a șters: %s", traducere) % (nume, eroare[0]), True)
		return "renuntat"

	def gata(rezultat):
		_uita(cale)
		if rezultat and rezultat.get("reusit"):
			anunta(_t("Tema %s a fost ștearsă.", traducere) % nume)
		else:
			anunta(_t("Tema %s nu s-a șters: %s", traducere) % (nume, (rezultat or {}).get("stare") or ""), True)

	(porneste or _pornesteLucrarea)(pl, gata)
	return "pachet"


def _pornesteLucrarea(pl, gata):
	"""Lucrarea opkg a Extensiilor (se vede si in pagina web); `gata(rezultat)` la sfarsit"""
	L = _L()
	try:
		from Components.PluginComponent import plugins
	except ImportError:
		plugins = None
	l = L.pornesteLucrarea(pl, plugins=plugins, din_web=False)

	def asculta(fel, *date):
		if fel == "gata":
			l.lasa(asculta)
			gata(l.rezultat)
	l.asculta(asculta)
	return l
