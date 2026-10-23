# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# navigator_web.py: „Navigator web” in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Media > Navigator web (Plugins/Extensions/HdsNavigator), butonul Albastru din ecranul camului,
# meniul navigatorului si Setari > Surse Internet > „Setări navigator web”. Aici, aceleasi lucruri:
#   - starea navigatorului de pe televizor (deschis sau nu, modul, felul desenului, campul activ, marirea), fara adrese;
#   - textul scris aici ajunge in campul de text activ de pe televizor (in navigator sau intr-o fereastra de text a
#     enigma2: Plugins/Extensions/HdsNavigator/campuri.py). Numai dintr-un browser asociat (cookie + antetul CSRF),
#     niciodata cu ?token=; textul sta numai in corpul cererii si nu se scrie in niciun jurnal;
#   - „Deschide pe televizor” pentru o adresa scrisa aici, pentru pagina de pornire si pentru interfata camului;
#   - setarile (aceleasi setari config.plugins.hdsnavigator ca pe televizor), favoritele, stergerea datelor;
#   - HbbTV: semnul rosu din bara si "Șterge datele HbbTV" (datele aplicatiilor HbbTV ale canalelor);
#     "Pornirea automată a aplicațiilor HbbTV" (ca pe televizor); o aplicatie pornita automat si inca
#     nevazuta nu e "navigatorul deschis": deschiderea si stergerile o opresc pe loc (lansator.cedeaza);
#     "HbbTV clar" (desenul la marimea intreaga, oprit din fabrica), ca pe televizor, de la urmatoarea pornire a
#     aplicatiei;
#   - chenarul pe selectie si stilul lui (0.2.7): culoarea, forma, grosimea, pulsul, viteza, ca pe
#     televizor (randurile stilului se vad numai cu chenarul pornit, viteza numai cu pulsul pornit); cu navigatorul
#     deschis pe televizor, chenarul se schimba pe loc (Navigator.schimbaChenar).
#
# O SINGURA LOGICA: setarile, favoritele si stergerea sunt in Plugins/Extensions/HdsNavigator/setari.py, textul in
# campuri.py, starea in lansator.py; paginile nu le scriu a doua oara.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/navigator                        starea, setarile cu alegerile, favoritele, unde ar ajunge textul
#   POST /api/navigator-text                   text=... (in corp): in campul activ de pe televizor; fara ?token=
#   POST /api/navigator-deschide               adresa=... (gol: pagina de pornire): navigatorul pe televizor
#   POST /api/navigator-cam                    port=... (cand camul are mai multe): interfata web a camului pe televizor
#   POST /api/navigator-inchide                inchide navigatorul de pe televizor
#   POST /api/navigator-seteaza                pagina_pornire, marire, font_minim, desen, chenar (1|0), chenar_culoare,
#                                              chenar_forma, chenar_grosime, chenar_puls (1|0), chenar_viteza (oricare)
#   POST /api/navigator-favorit-adauga         adresa, titlu
#   POST /api/navigator-favorit-sterge         index
#   POST /api/navigator-sterge-datele          confirmat=1
#   POST /api/navigator-sterge-hbbtv           confirmat=1 (cu aplicatia HbbTV inchisa)
#   (navigator-seteaza primeste si hbbtv=1|0, setarea principala HbbTV, hbbtv_semn=1|0, hbbtv_autostart=1|0 si
#   hbbtv_clar=1|0;
#   GET /api/navigator da in hbbtv.ultima motivul ultimei aplicatii HbbTV care nu s-a deschis, ca pe televizor:
#   Components/HdsHbbtvPornire.ultima)
#   GET  /navigator                            pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; nimic nu asteapta (fisierul favoritelor e mic).

SETARI = ("pagina_pornire", "marire", "font_minim", "desen", "chenar", "chenar_culoare", "chenar_forma", "chenar_grosime",
	"chenar_puls", "chenar_viteza")
ALEGERI = ("marire", "font_minim", "desen", "chenar_culoare", "chenar_forma", "chenar_grosime", "chenar_viteza")
DA_NU = ("chenar", "chenar_puls")
CHENAR = ("chenar", "chenar_culoare", "chenar_forma", "chenar_grosime", "chenar_puls", "chenar_viteza")
# randurile care se vad numai cand alte setari au o anumita valoare (ca pe televizor, setari.randuriChenar)
DEPINDE = {
	"chenar_culoare": [["chenar", "1"]],
	"chenar_forma": [["chenar", "1"]],
	"chenar_grosime": [["chenar", "1"]],
	"chenar_puls": [["chenar", "1"]],
	"chenar_viteza": [["chenar", "1"], ["chenar_puls", "1"]],
}
MAX_VALOARE = 2048
MAX_TEXT = 4096


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


class Legaturi(object):
	"""Modulele pluginului HdsNavigator si deschiderea ecranelor; probele de pe PC dau altele."""

	def __init__(self):
		from Plugins.Extensions.HdsNavigator import setari, lansator, campuri
		self.S = setari
		self.L = lansator
		self.campuri = campuri

	def deschide(self, sesiune, adresa):
		from Plugins.Extensions.HdsNavigator.plugin import deschideNavigator
		return deschideNavigator(sesiune, adresa)

	def deschideCam(self, sesiune, port=None):
		from Plugins.Extensions.HdsNavigator.plugin import deschideInterfataCam
		return deschideInterfataCam(sesiune, port)

	def instalat(self):
		import os
		return os.path.exists(self.L.CALE_LANSATOR)

	def ultimaHbbtv(self):
		from Components import HdsHbbtvPornire
		return HdsHbbtvPornire.ultima()


_legaturi = [None]


def _n(N=None):
	if N is not None:
		return N
	if _legaturi[0] is None:
		_legaturi[0] = Legaturi()
	return _legaturi[0]


TEXTE_STARE = {
	"oprit": N_("Navigatorul nu este deschis pe televizor."),
	"pornire": N_("Navigatorul pornește pe televizor."),
	"incarcare": N_("Se încarcă pagina pe televizor."),
	"aratat": N_("Navigatorul este pe ecranul televizorului."),
	"ascuns": N_("Pe televizor e deschisă o fereastră peste navigator."),
	"oprire": N_("Navigatorul se închide."),
}

TEXTE_TINTA = {
	"tastatura": N_("Textul ajunge în tastatura deschisă pe televizor."),
	"caseta": N_("Textul ajunge în caseta de text deschisă pe televizor."),
	"setare": N_("Textul ajunge în setarea de text aleasă pe televizor."),
	"navigator": N_("Textul ajunge în câmpul ales în pagina de pe televizor."),
	None: N_("Pe televizor nu e deschis niciun câmp de text."),
}

TEXTE_CAMP = {
	"niciunul": N_("niciun câmp"),
	"text": N_("câmp de text"),
	"parola": N_("câmp de parolă"),
	"numar": N_("câmp de număr"),
	"zona": N_("text pe mai multe rânduri"),
}


def _alegeri(element):
	rez = []
	for x in element.choices.choices:
		if isinstance(x, tuple):
			rez.append([str(x[0]), _t(x[1])])
		else:
			rez.append([str(x), _t(str(x))])
	return rez


def stare(N=None, sesiune=None):
	"""Pentru GET /api/navigator. Fara adrese de pagini si fara texte din pagini."""
	N = _n(N)
	c = N.S.initConfig()
	nav = N.L.activ()
	if nav is not None and getattr(getattr(nav, "a", None), "fundal", False) is True:
		nav = None   # aplicatia HbbTV pornita automat, inca nevazuta
	st = nav.stareWeb() if nav is not None else {"stare": "oprit", "mod": "", "desen": "", "rezerva": "", "camp": "niciunul", "marire": 0}
	fel, parola = N.campuri.tinta(sesiune)
	setari = {"pagina_pornire": {"eticheta": _t(N.S.ETICHETE["pagina_pornire"]), "valoare": c.pagina_pornire.value,
		"descriere": _t(N.S.DESCRIERI["pagina_pornire"])}}
	for nume in ALEGERI:
		element = getattr(c, nume)
		setari[nume] = {"eticheta": _t(N.S.ETICHETE[nume]), "valoare": str(element.value), "alegeri": _alegeri(element),
			"descriere": _t(N.S.DESCRIERI[nume])}
	for nume in DA_NU:
		setari[nume] = {"eticheta": _t(N.S.ETICHETE[nume]), "valoare": "1" if getattr(c, nume).value else "0",
			"alegeri": [["1", _t("Yes")], ["0", _t("No")]], "descriere": _t(N.S.DESCRIERI[nume])}
	for nume, conditii in DEPINDE.items():
		setari[nume]["depinde"] = conditii
	return {
		"result": True,
		"instalat": bool(N.instalat()),
		"navigator": st,
		"text_stare": _t(TEXTE_STARE.get(st["stare"], "")),
		"text_camp": _t(TEXTE_CAMP.get(st.get("camp"), TEXTE_CAMP["niciunul"])),
		"tinta": {"fel": fel, "parola": bool(parola), "text": _t(TEXTE_TINTA.get(fel, TEXTE_TINTA[None]))},
		"ordine": list(SETARI),
		"setari": setari,
		"favorite": N.S.citesteFavorite(),
		"hbbtv": {"pornit": {"eticheta": _t(N.S.ETICHETE["hbbtv"]), "valoare": bool(c.hbbtv.value),
			"descriere": _t(N.S.DESCRIERI["hbbtv"])},
			"semn": {"eticheta": _t(N.S.ETICHETE["hbbtv_semn"]), "valoare": bool(c.hbbtv_semn.value),
			"descriere": _t(N.S.DESCRIERI["hbbtv_semn"])},
			"autostart": {"eticheta": _t(N.S.ETICHETE["hbbtv_autostart"]), "valoare": bool(c.hbbtv_autostart.value),
			"descriere": _t(N.S.DESCRIERI["hbbtv_autostart"])},
			"clar": {"eticheta": _t(N.S.ETICHETE["hbbtv_clar"]), "valoare": bool(c.hbbtv_clar.value),
			"descriere": _t(N.S.DESCRIERI["hbbtv_clar"])},
			"ultima": _ultimaHbbtv(N)},
	}


def _ultimaHbbtv(N):
	"""Motivul ultimei aplicatii HbbTV care nu a pornit, s-a inchis singura sau nu s-a aratat (text tradus, fara adrese),
	sau None."""
	f = getattr(N, "ultimaHbbtv", None)
	if f is None:
		return None
	try:
		u = f()
	except Exception as e:
		print("[HdsWebControl] navigator: ultima aplicatie HbbTV: %s" % e)
		return None
	if not u:
		return None
	return {"text": _t(u.get("text") or ""), "ora": u.get("ora") or "", "motiv": u.get("motiv") or ""}


def _activ(N):
	"""Navigatorul deschis pe televizor, dupa ce o aplicatie HbbTV pornita automat si inca nevazuta a lasat locul
	(lansator.cedeaza)."""
	f = getattr(N.L, "cedeaza", None)
	return f() if f is not None else N.L.activ()


def _cuStare(rez, N, sesiune):
	s = stare(N, sesiune)
	s.update(rez)
	return s


def trimiteText(argumente, N=None, sesiune=None):
	"""POST /api/navigator-text: textul numai in corp; raspunsul nu il repeta."""
	N = _n(N)
	text = argumente.get("text", "")
	if not text:
		return _cuStare({"result": False, "message": _t("Scrie întâi textul.")}, N, sesiune)
	if len(text) > MAX_TEXT:
		return _cuStare({"result": False, "message": _t("Textul este prea lung (cel mult %d de semne).") % MAX_TEXT}, N, sesiune)
	# fara semne de control, in afara de randul nou (campurile cu mai multe randuri)
	text = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 0x20)
	ok, fel = N.campuri.trimite(sesiune, text)
	if ok:
		return _cuStare({"result": True, "message": _t("Textul a fost trimis pe televizor.")}, N, sesiune)
	motive = {
		"fara-camp": TEXTE_TINTA[None],
		"navigator": N_("Navigatorul nu este pe ecran acum."),
		"gol": N_("Scrie întâi textul."),
	}
	return _cuStare({"result": False, "message": _t(motive.get(fel, N_("Textul nu a ajuns pe televizor.")))}, N, sesiune)


def deschide(argumente, N=None, sesiune=None):
	"""POST /api/navigator-deschide: adresa pe televizor; cu navigatorul deschis, pagina se schimba in el."""
	N = _n(N)
	if sesiune is None:
		return _cuStare({"result": False, "message": _t("Interfața web nu are încă legătura cu televizorul. Încearcă peste câteva secunde.")}, N, sesiune)
	text = argumente.get("adresa", "")
	adresa = N.S.adresaBuna(text) if text else ""
	if text and not adresa:
		return _cuStare({"result": False, "message": _t("Adresa nu se poate deschide.")}, N, sesiune)
	nav = _activ(N)
	if nav is not None:
		if nav.mod != N.L.MOD_OBISNUIT:
			return _cuStare({"result": False, "message": _t("Pe televizor e deschisă interfața camului. Închide-o întâi.")}, N, sesiune)
		if not adresa:
			adresa = N.S.adresaBuna(N.S.initConfig().pagina_pornire.value) or N.S.PAGINA_IMPLICITA
		nav.url(adresa)
		return _cuStare({"result": True, "message": _t("Pagina se deschide în navigatorul de pe televizor.")}, N, sesiune)
	N.deschide(sesiune, adresa or None)
	return _cuStare({"result": True, "message": _t("Navigatorul se deschide pe televizor.")}, N, sesiune)


def deschideCam(argumente, N=None, sesiune=None):
	"""POST /api/navigator-cam: acelasi lucru ca butonul Albastru din ecranul camului."""
	N = _n(N)
	if sesiune is None:
		return _cuStare({"result": False, "message": _t("Interfața web nu are încă legătura cu televizorul. Încearcă peste câteva secunde.")}, N, sesiune)
	if _activ(N) is not None:
		return _cuStare({"result": False, "message": _t("Navigatorul este deja deschis pe televizor. Închide-l întâi.")}, N, sesiune)
	port = argumente.get("port", "")
	N.deschideCam(sesiune, int(port) if port.isdigit() and 0 < int(port) < 65536 else None)
	return _cuStare({"result": True, "message": _t("Interfața camului se deschide pe televizor.")}, N, sesiune)


def inchide(argumente, N=None, sesiune=None):
	N = _n(N)
	nav = N.L.activ()
	if nav is None:
		return _cuStare({"result": False, "message": _t("Navigatorul nu este deschis pe televizor.")}, N, sesiune)
	nav.opreste()
	return _cuStare({"result": True, "message": _t("Navigatorul se închide pe televizor.")}, N, sesiune)


def _valoareAleasa(element, text):
	for x in element.choices.choices:
		valoare = x[0] if isinstance(x, tuple) else x
		if str(valoare) == text:
			return valoare
	return None


def seteaza(argumente, N=None, sesiune=None, configfile=None):
	"""POST /api/navigator-seteaza: toate valorile primite trebuie sa fie bune, altfel nu se schimba nimic."""
	N = _n(N)
	c = N.S.initConfig()
	noi = {}
	for nume in ("hbbtv", "hbbtv_semn", "hbbtv_autostart", "hbbtv_clar") + DA_NU:
		if nume not in argumente:
			continue
		if argumente[nume] not in ("0", "1"):
			return _cuStare({"result": False, "message": _t("Alegerea „%s” nu există pentru „%s”.") % (
				argumente[nume][:40], _t(N.S.ETICHETE[nume]))}, N, sesiune)
		noi[nume] = argumente[nume] == "1"
	if "pagina_pornire" in argumente:
		a = N.S.adresaBuna(argumente["pagina_pornire"])
		if not a:
			return _cuStare({"result": False, "message": _t("Adresa paginii de pornire nu se poate deschide.")}, N, sesiune)
		noi["pagina_pornire"] = a
	for nume in ALEGERI:
		if nume in argumente:
			v = _valoareAleasa(getattr(c, nume), argumente[nume])
			if v is None:
				return _cuStare({"result": False, "message": _t("Alegerea „%s” nu există pentru „%s”.") % (
					argumente[nume][:40], _t(N.S.ETICHETE[nume]))}, N, sesiune)
			noi[nume] = v
	if not noi:
		return _cuStare({"result": False, "message": _t("Nu s-a trimis nicio setare.")}, N, sesiune)
	schimbate = set(nume for nume, v in noi.items() if getattr(c, nume).value != v)
	for nume, v in noi.items():
		e = getattr(c, nume)
		e.value = v
		e.save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	if schimbate & set(("hbbtv", "hbbtv_autostart")):
		try:
			# HbbTV si pornirea automata se aplica pe loc pe televizor (Components/HdsHbbtvPornire.setari_salvate)
			from Components import HdsHbbtvPornire
			HdsHbbtvPornire.setari_salvate()
		except Exception as e:
			print("[HdsWebControl] navigator: setarile HbbTV: %s" % e)
	mesaj = _t("Salvat.")
	nav = N.L.activ()
	chenar_pe_loc = False
	if nav is not None and schimbate & set(CHENAR) and nav.mod != N.L.MOD_HBBTV:
		# chenarul si stilul lui se vad pe loc in navigatorul deschis pe televizor
		chenar_pe_loc = nav.schimbaChenar(N.S.setariChenar(c))
	if chenar_pe_loc and schimbate - set(CHENAR):
		mesaj += " " + _t("Chenarul se schimbă acum pe televizor; celelalte setări se folosesc la următoarea deschidere a navigatorului.")
	elif chenar_pe_loc:
		mesaj += " " + _t("Chenarul se schimbă acum pe televizor.")
	elif nav is not None and schimbate:
		mesaj += " " + _t("Se folosește la următoarea deschidere a navigatorului.")
	return _cuStare({"result": True, "message": mesaj}, N, sesiune)


def adaugaFavorit(argumente, N=None, sesiune=None):
	N = _n(N)
	ok, mesaj = N.S.adaugaFavorit(argumente.get("adresa", ""), argumente.get("titlu", ""))
	return _cuStare({"result": ok, "message": mesaj}, N, sesiune)


def stergeFavorit(argumente, N=None, sesiune=None):
	N = _n(N)
	try:
		index = int(argumente.get("index", ""))
	except ValueError:
		return _cuStare({"result": False, "message": _t("Pagina nu mai este în favorite.")}, N, sesiune)
	ok, mesaj = N.S.stergeFavorit(index)
	return _cuStare({"result": ok, "message": mesaj}, N, sesiune)


def stergeDatele(argumente, N=None, sesiune=None):
	N = _n(N)
	if argumente.get("confirmat") != "1":
		return _cuStare({"result": False, "message": _t("Se cere confirmarea (confirmat=1).")}, N, sesiune)
	if _activ(N) is not None:
		return _cuStare({"result": False, "message": _t("Închide întâi navigatorul, apoi șterge datele.")}, N, sesiune)
	N.S.stergeDatele()
	print("[HdsWebControl] navigator: datele de navigare sterse (din web)")
	return _cuStare({"result": True, "message": _t("Datele de navigare au fost șterse.")}, N, sesiune)


def stergeHbbtv(argumente, N=None, sesiune=None):
	"""POST /api/navigator-sterge-hbbtv: datele aplicatiilor HbbTV (ca pe televizor, Setari navigator web)."""
	N = _n(N)
	if argumente.get("confirmat") != "1":
		return _cuStare({"result": False, "message": _t("Se cere confirmarea (confirmat=1).")}, N, sesiune)
	nav = _activ(N)
	if nav is not None:
		text = N_("Închide întâi aplicația HbbTV, apoi șterge datele.") if nav.mod == N.L.MOD_HBBTV else \
			N_("Închide întâi navigatorul, apoi șterge datele.")
		return _cuStare({"result": False, "message": _t(text)}, N, sesiune)
	N.S.stergeDateleHbbtv()
	print("[HdsWebControl] navigator: datele HbbTV sterse (din web)")
	return _cuStare({"result": True, "message": _t("Datele HbbTV au fost șterse.")}, N, sesiune)


def argumente(request, permise=SETARI + ("adresa", "titlu", "index", "confirmat", "port", "hbbtv", "hbbtv_semn",
		"hbbtv_autostart", "hbbtv_clar"),
		maxim=MAX_VALOARE):
	"""Argumentele cererii (adresa sau corpul formularului), fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:maxim].strip()
	return rez


def cuJeton(request):
	"""Cererea poarta ?token= (sau token in corp): textul nu se primeste asa, numai din browserul asociat."""
	return any((k.decode("utf-8", "replace") if isinstance(k, bytes) else k) == "token"
		for k in (getattr(request, "args", None) or {}))


def rute(baza, resource, sesiune=None, N=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/navigator: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(N, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TextResource(baza):
		"""POST /api/navigator-text: numai cu cookie-ul unui browser asociat; textul nu apare in nicio eroare."""
		schimbaCeva = True

		def render_POST(self, request):
			if cuJeton(request):
				return self._eroare(request, _t("Textul se trimite numai dintr-un browser asociat."), 403)
			try:
				arg = argumente(request, permise=("text",), maxim=MAX_TEXT + 1)
				return self._raspunde(request, trimiteText(arg, N, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare.__class__.__name__, 500)

		def render_GET(self, request):
			request.setHeader(b"allow", b"POST")
			return self._eroare(request, _t("Textul se trimite numai prin POST, din pagina „Navigator web”."), 405)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), N=N, sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class DeschideResource(_Schimba):
		lucru = staticmethod(deschide)

	class CamResource(_Schimba):
		lucru = staticmethod(deschideCam)

	class InchideResource(_Schimba):
		lucru = staticmethod(inchide)

	class SeteazaResource(_Schimba):
		lucru = staticmethod(seteaza)

	class FavoritAdaugaResource(_Schimba):
		lucru = staticmethod(adaugaFavorit)

	class FavoritStergeResource(_Schimba):
		lucru = staticmethod(stergeFavorit)

	class StergeDateleResource(_Schimba):
		lucru = staticmethod(stergeDatele)

	class StergeHbbtvResource(_Schimba):
		lucru = staticmethod(stergeHbbtv)

	class PaginaResource(resource.Resource):
		"""GET /navigator: pagina „Navigator web”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"navigator": StareResource(),
		b"navigator-text": TextResource(),
		b"navigator-deschide": DeschideResource(),
		b"navigator-cam": CamResource(),
		b"navigator-inchide": InchideResource(),
		b"navigator-seteaza": SeteazaResource(),
		b"navigator-favorit-adauga": FavoritAdaugaResource(),
		b"navigator-favorit-sterge": FavoritStergeResource(),
		b"navigator-sterge-datele": StergeDateleResource(),
		b"navigator-sterge-hbbtv": StergeHbbtvResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /procesor si /limbi."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


ETICHETE = {
	"TITLU": N_("Navigator web"),
	"INCARCARE": N_("Se citește starea..."),
	"PE_TV": N_("Pe televizor"),
	"TEXT": N_("Text trimis pe televizor"),
	"TEXT_NOTA": N_("Scrie aici un text lung (o adresă, o parolă, un mesaj) și trimite-l în câmpul ales pe televizor. Textul nu se păstrează nicăieri."),
	"TRIMITE": N_("Trimite pe televizor"),
	"DESCHIDE": N_("Deschide pe televizor"),
	"ADRESA": N_("Adresa paginii"),
	# campul "Deschide pe televizor": un cuvant fara punct merge la cautarea Google (HdsNavigator/setari.adresaBuna)
	"ADRESA_CAUTARE": N_("Adresa paginii sau cuvintele de căutat cu Google"),
	"ACASA": N_("Pagina de pornire pe televizor"),
	"CAM": N_("Interfața camului pe televizor"),
	"INCHIDE": N_("Închide navigatorul de pe televizor"),
	"SETARI": N_("Setări"),
	"SALVEAZA": N_("Salvează"),
	"FAVORITE": N_("Favorite"),
	"TITLU_FAV": N_("Numele paginii (dacă vrei)"),
	"ADAUGA": N_("Adaugă la favorite"),
	"FARA_FAV": N_("Nu ai pagini favorite."),
	"DATE": N_("Datele de navigare"),
	"DATE_NOTA": N_("Cookie-urile, datele siturilor și mărirea ținută minte pe fiecare sit. Favoritele rămân."),
	"STERGE_DATE": N_("Șterge datele de navigare"),
	"HBBTV": N_("HbbTV"),
	"HBBTV_NOTA": N_("Aplicațiile HbbTV ale canalelor pornesc cu ROȘU sau Portal pe canal. Datele lor (cookie-urile, alegerea din fereastra de consimțământ) sunt separate de ale navigatorului."),
	"STERGE_HBBTV": N_("Șterge datele HbbTV"),
	"HBBTV_ULTIMA": N_("Ultima aplicație HbbTV care nu s-a deschis"),
	"NEINSTALAT": N_("Navigatorul lipsește din imaginea acestui receptor, deci nu se poate deschide pe televizor."),
}

NOTA_MENIU = N_("Aceleași setări sunt pe televizor, în %s.")

TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"se_trimite": N_("Se trimite..."),
	"se_salveaza": N_("Se salvează..."),
	"deschide": N_("Deschide pe televizor"),
	"scoate": N_("Scoate"),
	"confirma_sterge": N_("Ștergi datele de navigare?"),
	"confirma_hbbtv": N_("Ștergi datele aplicațiilor HbbTV?"),
	"da": N_("Yes"),
	"nu": N_("No"),
	"desen": N_("Desenul: %s"),
	"marire": N_("Mărirea: %s %%"),
	"camp": N_("Câmpul ales în pagină: %s"),
	"parola_tv": N_("Pe televizor e ales un câmp de parolă: textul nu se vede pe ecran."),
}


def _json(obiect):
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina):
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=False))
	nota = html.escape(_t(NOTA_MENIU), quote=False)
	nota = nota.replace("%s", _drumMeniu("hds_navigator_setari"), 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", _limba()).replace("__NOTA_MENIU__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,300px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  select,input,textarea{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;box-sizing:border-box;}
  textarea{min-height:110px;resize:vertical;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .fav{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .fav:last-child{border-bottom:0;}
  .fav .adr{color:var(--text-slab);font-size:.82rem;word-break:break-all;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .fav{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <p class="mesaj ascuns eroare" id="neinstalat">__T_NEINSTALAT__</p>
  <section class="card">
    <h2>__T_PE_TV__</h2>
    <p id="stareTv"></p>
    <p class="nota" id="detaliiTv"></p>
    <div class="butoane">
      <button type="button" id="acasa">__T_ACASA__</button>
      <button type="button" id="cam">__T_CAM__</button>
      <button type="button" id="inchide">__T_INCHIDE__</button>
    </div>
    <p class="mesaj" id="mesajTv"></p>
  </section>
  <section class="card">
    <h2>__T_TEXT__</h2>
    <p class="nota">__T_TEXT_NOTA__</p>
    <p id="tinta"></p>
    <textarea id="text" autocomplete="off" spellcheck="false"></textarea>
    <div class="butoane"><button type="button" class="verde" id="trimite">__T_TRIMITE__</button></div>
    <p class="mesaj" id="mesajText"></p>
  </section>
  <section class="card">
    <h2>__T_DESCHIDE__</h2>
    <label for="adresa">__T_ADRESA_CAUTARE__</label>
    <input id="adresa" type="text" autocomplete="off" placeholder="https://">
    <div class="butoane"><button type="button" class="albastru" id="deschide">__T_DESCHIDE__</button></div>
    <p class="mesaj" id="mesajAdresa"></p>
  </section>
  <section class="card">
    <h2>__T_SETARI__</h2>
    <div id="setari"></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">__T_SALVEAZA__</button></div>
    <p class="mesaj" id="mesajSetari"></p>
    <p class="nota">__NOTA_MENIU__</p>
  </section>
  <section class="card">
    <h2>__T_FAVORITE__</h2>
    <div id="favorite"></div>
    <p class="nota ascuns" id="faraFav">__T_FARA_FAV__</p>
    <label for="favAdresa">__T_ADRESA__</label>
    <input id="favAdresa" type="url" inputmode="url" autocomplete="off" placeholder="https://">
    <label for="favTitlu">__T_TITLU_FAV__</label>
    <input id="favTitlu" type="text" autocomplete="off">
    <div class="butoane"><button type="button" id="adauga">__T_ADAUGA__</button></div>
    <p class="mesaj" id="mesajFav"></p>
  </section>
  <section class="card">
    <h2>__T_HBBTV__</h2>
    <p class="nota">__T_HBBTV_NOTA__</p>
    <div class="rand">
      <div><label for="hbbtvPornit" id="hbbtvPornitEticheta"></label><p class="nota" id="hbbtvPornitDescriere"></p></div>
      <select id="hbbtvPornit"></select>
    </div>
    <div class="rand" id="randHbbtvSemn">
      <div><label for="hbbtvSemn" id="hbbtvEticheta"></label><p class="nota" id="hbbtvDescriere"></p></div>
      <select id="hbbtvSemn"></select>
    </div>
    <div class="rand" id="randHbbtvAutostart">
      <div><label for="hbbtvAutostart" id="hbbtvAutostartEticheta"></label><p class="nota" id="hbbtvAutostartDescriere"></p></div>
      <select id="hbbtvAutostart"></select>
    </div>
    <div class="rand" id="randHbbtvClar">
      <div><label for="hbbtvClar" id="hbbtvClarEticheta"></label><p class="nota" id="hbbtvClarDescriere"></p></div>
      <select id="hbbtvClar"></select>
    </div>
    <div class="ascuns" id="hbbtvUltima"><p class="nota">__T_HBBTV_ULTIMA__</p><p id="hbbtvUltimaText"></p></div>
    <div class="butoane">
      <button type="button" class="verde" id="hbbtvSalveaza">__T_SALVEAZA__</button>
      <button type="button" id="stergeHbbtv">__T_STERGE_HBBTV__</button>
    </div>
    <p class="mesaj" id="mesajHbbtv"></p>
  </section>
  <section class="card">
    <h2>__T_DATE__</h2>
    <p class="nota">__T_DATE_NOTA__</p>
    <div class="butoane"><button type="button" id="stergeDate">__T_STERGE_DATE__</button></div>
    <p class="mesaj" id="mesajDate"></p>
  </section>
</div>
</main>
<script>
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
var ultim = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
function mesaj(id, text, eroare){ var m = $(id); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function arataSetari(d){
  var s = $("setari");
  if(s.contains(document.activeElement)){ return; }
  s.textContent = "";
  (d.ordine || []).forEach(function(nume){
    var x = d.setari[nume]; if(!x){ return; }
    var r = document.createElement("div"); r.className = "rand";
    var l = document.createElement("label"); l.htmlFor = "s_" + nume; l.textContent = x.eticheta;
    var c;
    if(x.alegeri){
      c = document.createElement("select");
      x.alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; c.appendChild(o); });
    } else { c = document.createElement("input"); c.type = "url"; c.autocomplete = "off"; }
    c.id = "s_" + nume; c.value = x.valoare; c.dataset.nume = nume;
    if(x.depinde){ r.dataset.depinde = JSON.stringify(x.depinde); }
    if(x.alegeri){ c.addEventListener("change", potriveste); }
    var n = document.createElement("p"); n.className = "nota"; n.textContent = x.descriere || "";
    var st = document.createElement("div"); st.appendChild(l); st.appendChild(n);
    r.appendChild(st); r.appendChild(c); s.appendChild(r);
  });
  potriveste();
}
// randurile stilului chenarului: numai cu chenarul pornit (viteza numai cu pulsul pornit), ca pe televizor
function potriveste(){
  Array.prototype.forEach.call($("setari").querySelectorAll(".rand[data-depinde]"), function(r){
    var bun = JSON.parse(r.dataset.depinde).every(function(d){ var c = $("s_" + d[0]); return !c || c.value === d[1]; });
    r.classList.toggle("ascuns", !bun);
  });
}
function arataFavorite(d){
  var f = $("favorite"); f.textContent = "";
  var lista = d.favorite || [];
  $("faraFav").classList.toggle("ascuns", lista.length > 0);
  lista.forEach(function(x, i){
    var r = document.createElement("div"); r.className = "fav";
    var t = document.createElement("div");
    var a = document.createElement("div"); a.textContent = x.titlu || x.adresa;
    var b = document.createElement("div"); b.className = "adr"; b.textContent = x.adresa;
    t.appendChild(a); t.appendChild(b);
    var d1 = document.createElement("button"); d1.type = "button"; d1.textContent = TXT.deschide;
    d1.addEventListener("click", function(){ deschide(x.adresa, "mesajFav"); });
    var d2 = document.createElement("button"); d2.type = "button"; d2.textContent = TXT.scoate;
    d2.addEventListener("click", function(){
      var q = new URLSearchParams(); q.set("index", String(i));
      cerere("/api/navigator-favorit-sterge", "POST", q).then(function(d){ mesaj("mesajFav", d.message, !d.result); arata(d); })
        .catch(function(){ mesaj("mesajFav", TXT.nu_raspunde, true); });
    });
    r.appendChild(t); r.appendChild(d1); r.appendChild(d2); f.appendChild(r);
  });
}
function arata(d){
  if(!d || !d.navigator){ return; }
  ultim = d;
  $("neinstalat").classList.toggle("ascuns", !!d.instalat);
  var n = d.navigator;
  $("stareTv").textContent = d.text_stare || "";
  var det = [];
  if(n.stare !== "oprit"){
    if(n.desen){ det.push(TXT.desen.replace("%s", n.desen)); }
    if(n.marire){ det.push(TXT.marire.replace("%s", n.marire)); }
    det.push(TXT.camp.replace("%s", d.text_camp || ""));
  }
  $("detaliiTv").textContent = det.join(" · ");
  $("inchide").disabled = n.stare === "oprit";
  $("tinta").textContent = ((d.tinta && d.tinta.text) || "") + (d.tinta && d.tinta.parola ? " " + TXT.parola_tv : "");
  $("trimite").disabled = !(d.tinta && d.tinta.fel);
  arataSetari(d);
  arataFavorite(d);
  arataHbbtv(d);
}
function arataHbbtv(d){
  [["pornit", "hbbtvPornit", "hbbtvPornitEticheta", "hbbtvPornitDescriere"],
   ["semn", "hbbtvSemn", "hbbtvEticheta", "hbbtvDescriere"],
   ["autostart", "hbbtvAutostart", "hbbtvAutostartEticheta", "hbbtvAutostartDescriere"],
   ["clar", "hbbtvClar", "hbbtvClarEticheta", "hbbtvClarDescriere"]].forEach(function(r){
    var h = d.hbbtv && d.hbbtv[r[0]], s = $(r[1]);
    if(!h || document.activeElement === s){ return; }
    $(r[2]).textContent = h.eticheta;
    $(r[3]).textContent = h.descriere || "";
    if(!s.options.length){
      [["1", TXT.da], ["0", TXT.nu]].forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    }
    s.value = h.valoare ? "1" : "0";
  });
  var u = d.hbbtv && d.hbbtv.ultima;
  $("hbbtvUltima").classList.toggle("ascuns", !(u && u.text));
  $("hbbtvUltimaText").textContent = u && u.text ? (u.ora ? u.ora + " " : "") + u.text : "";
  potrivesteHbbtv();
}
// cu HbbTV oprit semnul rosu, pornirea automata si HbbTV clar nu se vad (ca pe televizor)
function potrivesteHbbtv(){
  var oprit = $("hbbtvPornit").value === "0";
  $("randHbbtvSemn").classList.toggle("ascuns", oprit);
  $("randHbbtvAutostart").classList.toggle("ascuns", oprit);
  $("randHbbtvClar").classList.toggle("ascuns", oprit);
}
$("hbbtvPornit").addEventListener("change", potrivesteHbbtv);
function citeste(){
  return cerere("/api/navigator").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || TXT.necitit; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = TXT.nu_raspunde_retea; });
}
function deschide(adr, idMesaj){
  var q = new URLSearchParams(); q.set("adresa", adr || "");
  mesaj(idMesaj, TXT.se_trimite);
  cerere("/api/navigator-deschide", "POST", q).then(function(d){ mesaj(idMesaj, d.message, !d.result); arata(d); })
    .catch(function(){ mesaj(idMesaj, TXT.nu_raspunde, true); });
}
function simplu(cale, idMesaj){
  mesaj(idMesaj, TXT.se_trimite);
  cerere(cale, "POST", new URLSearchParams()).then(function(d){ mesaj(idMesaj, d.message, !d.result); arata(d); })
    .catch(function(){ mesaj(idMesaj, TXT.nu_raspunde, true); });
}
$("trimite").addEventListener("click", function(){
  var t = $("text").value;
  if(!t){ return; }
  var q = new URLSearchParams(); q.set("text", t);
  mesaj("mesajText", TXT.se_trimite);
  cerere("/api/navigator-text", "POST", q).then(function(d){
    mesaj("mesajText", d.message, !d.result);
    if(d.result){ $("text").value = ""; }
    arata(d);
  }).catch(function(){ mesaj("mesajText", TXT.nu_raspunde, true); });
});
$("deschide").addEventListener("click", function(){ if($("adresa").value){ deschide($("adresa").value, "mesajAdresa"); } });
$("acasa").addEventListener("click", function(){ deschide("", "mesajTv"); });
$("cam").addEventListener("click", function(){ simplu("/api/navigator-cam", "mesajTv"); });
$("inchide").addEventListener("click", function(){ simplu("/api/navigator-inchide", "mesajTv"); });
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  Array.prototype.forEach.call($("setari").querySelectorAll("select,input"), function(c){ q.set(c.dataset.nume, c.value); });
  mesaj("mesajSetari", TXT.se_salveaza);
  cerere("/api/navigator-seteaza", "POST", q).then(function(d){
    mesaj("mesajSetari", d.message, !d.result);
    if(document.activeElement){ document.activeElement.blur(); }
    arata(d);
  }).catch(function(){ mesaj("mesajSetari", TXT.nu_raspunde, true); });
});
$("adauga").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("adresa", $("favAdresa").value); q.set("titlu", $("favTitlu").value);
  cerere("/api/navigator-favorit-adauga", "POST", q).then(function(d){
    mesaj("mesajFav", d.message, !d.result);
    if(d.result){ $("favAdresa").value = ""; $("favTitlu").value = ""; }
    arata(d);
  }).catch(function(){ mesaj("mesajFav", TXT.nu_raspunde, true); });
});
$("hbbtvSalveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("hbbtv_semn", $("hbbtvSemn").value);
  if($("hbbtvPornit").options.length){ q.set("hbbtv", $("hbbtvPornit").value); }
  if($("hbbtvAutostart").options.length){ q.set("hbbtv_autostart", $("hbbtvAutostart").value); }
  if($("hbbtvClar").options.length){ q.set("hbbtv_clar", $("hbbtvClar").value); }
  mesaj("mesajHbbtv", TXT.se_salveaza);
  cerere("/api/navigator-seteaza", "POST", q).then(function(d){
    mesaj("mesajHbbtv", d.message, !d.result);
    if(document.activeElement){ document.activeElement.blur(); }
    arata(d);
  }).catch(function(){ mesaj("mesajHbbtv", TXT.nu_raspunde, true); });
});
$("stergeHbbtv").addEventListener("click", function(){
  if(!confirm(TXT.confirma_hbbtv)){ return; }
  var q = new URLSearchParams(); q.set("confirmat", "1");
  cerere("/api/navigator-sterge-hbbtv", "POST", q).then(function(d){ mesaj("mesajHbbtv", d.message, !d.result); arata(d); })
    .catch(function(){ mesaj("mesajHbbtv", TXT.nu_raspunde, true); });
});
$("stergeDate").addEventListener("click", function(){
  if(!confirm(TXT.confirma_sterge)){ return; }
  var q = new URLSearchParams(); q.set("confirmat", "1");
  cerere("/api/navigator-sterge-datele", "POST", q).then(function(d){ mesaj("mesajDate", d.message, !d.result); arata(d); })
    .catch(function(){ mesaj("mesajDate", TXT.nu_raspunde, true); });
});
citeste();
setInterval(function(){ if(document.visibilityState === "visible"){ citeste(); } }, 3000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("https://"),
	),
	"js": (
		N_("browser deconectat"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
