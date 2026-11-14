# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRadioSetari.py: setarile ecranului radio (config.hds_radio) si semnul „ecranul radio se vede acum”.
#
# Aceleasi alegeri si aceleasi texte le folosesc ecranul de setari de pe televizor (Screens/HdsEcranRadio.py) si
# pagina web (Plugins/Extensions/HdsWebControl/radio_web.py): tabelele de aici sunt singura sursa.
#
# Fisierul nu importa nimic din enigma2 la incarcare: config.py se ia abia in initConfig(), ca probele de pe PC sa
# poata da config-ul lor. Textele din tabele sunt marcate cu N_ (xgettext, --keyword=N_) si se traduc la folosire.
#
# ecran_radio_vizibil(): True cat fereastra radio e aratata pe televizor. Il pot citi alte module (de exemplu
# mesajele de ecran negru ale barei) fara sa importe ecranul; il pune numai fereastra radio. ecran_numai_sunet():
# True cat fereastra radio e aratata pe un canal TV care trimite numai sunet (nu pe un post de radio).
#
# Canalele numai cu sunet (0.7.5, cererea unui tester pe IPTV): un canal TV (DVB sau IPTV) fara pista video, dar cu
# sunet, il recunoaste urmaritorul ecranului negru (Components/HdsEcranNegru.py, verdictul NUMAI_SUNET). Setarea
# „numai_sunet” spune ce se vede atunci: ecranul radio, protectia ecranului (Screens/ScreenSaver.py) sau amandoua
# (intai ecranul radio, apoi, dupa timpul ales, protectia). Timpul protectiei e setarea OE-Alliance
# config.usage.screenSaverStartTimer (secunde; 0 = oprita), aceeasi pentru toate cazurile protectiei; aici apare ca
# randul „protectie” (element(): randurile care nu sunt in config.hds_radio).


def N_(text):
	"""Marcaj pentru xgettext, fara efect: textul se traduce la folosire."""
	return text


# (valoare, text); ordinea e cea de pe ecran
VIZUALIZATOARE = (
	("oprit", N_("Oprit")),
	("bare", N_("Bare pe frecvențe")),
	("varfuri", N_("Bare cu vârfuri care cad încet")),
	("oglinda", N_("Spectru în oglindă")),
	("cerc", N_("Cerc")),
	("nivel", N_("Nivelul sunetului, stânga și dreapta")),
)
CULORI = (
	("skin", N_("Culorile ecranelor")),
	("clasic", N_("Clasice (verde, galben, roșu)")),
	("albastru", N_("Albastru")),
	("foc", N_("Foc")),
	("discret", N_("Discrete (gri)")),
)
# numarul de bare: cel mult cate benzi de fs/64 are sunetul, pe orice format (27 pana la 20 kHz), deci nimic inventat
BARE = (("12", "12"), ("16", "16"), ("24", "24"))
CADRE = (
	("10", N_("10 cadre pe secundă")),
	("15", N_("15 cadre pe secundă")),
	("20", N_("20 de cadre pe secundă")),
	("25", N_("25 de cadre pe secundă")),
)
ODIHNA = (
	("1", N_("După 1 minut fără taste")),       # 0.7.5 (ac.energ, forum 588 #2054)
	("5", N_("După 5 minute fără taste")),
	("10", N_("După 10 minute fără taste")),
	("15", N_("După 15 minute fără taste")),
	("30", N_("După 30 de minute fără taste")),
	("0", N_("Niciodată")),
)
EPG = (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"))
# ce se vede pe un canal TV care trimite numai sunet
NUMAI_SUNET = (
	("amandoua", N_("Ecranul radio, apoi protecția ecranului")),
	("radio", N_("Ecranul radio")),
	("protectie", N_("Protecția ecranului")),
)
# protectia ecranului: dupa cate secunde fara nicio tasta (valorile setarii OE-Alliance config.usage.screenSaverStartTimer)
PROTECTIE = (
	(0, N_("Niciodată")),
	(60, N_("După 1 minut fără taste")),
	(120, N_("După 2 minute fără taste")),
	(180, N_("După 3 minute fără taste")),
	(300, N_("După 5 minute fără taste")),
	(600, N_("După 10 minute fără taste")),
	(900, N_("După 15 minute fără taste")),
	(1200, N_("După 20 de minute fără taste")),
	(1800, N_("După 30 de minute fără taste")),
	(2700, N_("După 45 de minute fără taste")),
	(3600, N_("După o oră fără taste")),
)
PROTECTIE_IMPLICIT = 300
# ce arata protectia ecranului (config.usage.screenSaverMode, valorile OE-Alliance: 0 ecran negru, 1 sigla, 2 sigla
# canalului). Alte feluri (de pilda ceasuri sau imagini) se adauga aici si in Screens/ScreenSaver.py (FELURI).
# 3 (0.7.5, R075): screensaverul ales in meniul Screensaver (Screens/HdsScreensaver.py, Components/HdsScreensavere.py:
# ceasul, vremea, pozele, cerul ...); alegerea unuia din meniu sau din pagina web /screensaver pune singura felul 3,
# deci omul face un singur pas. Valoare peste cele OE-Alliance, ca pluginurile care citesc 0/1/2 sa nu fie incurcate.
PROTECTIE_FEL_ALES = 3
PROTECTIE_FEL = (
	(1, N_("Sigla HD Satelit")),
	(2, N_("Sigla canalului")),
	(0, N_("Ecran negru")),
	(PROTECTIE_FEL_ALES, N_("Screensaverul ales în meniul Screensaver")),
)
# randurile care nu stau in config.hds_radio: (sectiunea din config, numele OE-Alliance)
EXTERNE = {"protectie": ("usage", "screenSaverStartTimer")}

IMPLICITE = {
	"ecran": True,
	"taste_colorate": False,
	"vizualizator": "varfuri",
	"culori": "skin",
	"bare": "24",
	"cadre": "20",
	"odihna": "10",
	"epg": "3",
	"bara_la_zap": False,
	"numai_sunet": "amandoua",
	"protectie": PROTECTIE_IMPLICIT,
}

ORDINE = ("ecran", "taste_colorate", "vizualizator", "culori", "bare", "cadre", "odihna", "epg", "bara_la_zap",
	"numai_sunet", "protectie")
DA_NU = ("ecran", "taste_colorate", "bara_la_zap")
ALEGERI = {
	"vizualizator": VIZUALIZATOARE,
	"culori": CULORI,
	"bare": BARE,
	"cadre": CADRE,
	"odihna": ODIHNA,
	"epg": EPG,
	"numai_sunet": NUMAI_SUNET,
	"protectie": PROTECTIE,
}

ETICHETE = {
	"ecran": N_("Ecranul radio pe tot ecranul"),
	"taste_colorate": N_("Culorile comandă ecranul radio"),
	"vizualizator": N_("Vizualizatorul"),
	"culori": N_("Culorile"),
	"bare": N_("Numărul de bare"),
	"cadre": N_("Fluiditatea"),
	"odihna": N_("Ecranul de odihnă"),
	"epg": N_("Emisiunile următoare"),
	"bara_la_zap": N_("Bara la schimbarea postului"),
	"numai_sunet": N_("La canalele numai cu sunet"),
	"protectie": N_("Protecția ecranului"),
}

# fraza simpla intai; explicatia tehnica, daca e utila, dupa ea
DESCRIERI = {
	"ecran": N_("Când asculți un post de radio, ecranul arată numele postului, emisiunile, piesa, sunetul și semnalul. Cu Nu rămâne ecranul obișnuit."),
	"taste_colorate": N_("Cu Da, verde deschide egalizatorul, galben schimbă vizualizatorul și albastru paleta. Cu Nu, culorile păstrează comenzile comune de vizionare. Ecranul radio poate rămâne vizibil."),
	"vizualizator": N_("Cum se arată muzica pe ecran. Galben trece la următoarea numai dacă ai activat comenzile colorate ale radioului. Barele urmăresc sunetul adevărat al postului."),
	"culori": N_("Culorile barelor. Albastru trece la următoarele numai dacă ai activat comenzile colorate ale radioului. Alegerea skin folosește culorile meniurilor."),
	"bare": N_("Câte bare are vizualizatorul. Fiecare bară arată o parte din frecvențele sunetului. Barele se întind numai pe frecvențele pe care postul le transmite, deci pot fi mai puține."),
	"cadre": N_("De câte ori pe secundă se mișcă barele. Mai puține cadre încarcă mai puțin receptorul."),
	"odihna": N_("După atâtea minute fără nicio tastă rămân pe ecran doar numele postului, piesa și ceasul, care se mută încet, ca ecranul televizorului să nu se ardă. Orice tastă aduce ecranul întreg."),
	"epg": N_("Câte emisiuni următoare se arată sub emisiunea de acum, când postul transmite programul."),
	"bara_la_zap": N_("Cu Da, la schimbarea postului de radio apare și bara obișnuită de jos. Ecranul radio are deja toate datele."),
	"numai_sunet": N_("Unele canale TV, mai ales pe internet, trimit numai sunet. În locul ecranului negru se vede ecranul radio, protecția ecranului sau amândouă: întâi ecranul radio, apoi, după timpul ales mai jos, protecția. Tastele rămân cele de la televizor."),
	"protectie": N_("După atâtea minute fără nicio tastă, pe ecranul întunecat rămâne numai o siglă care se mută, ca televizorul să nu se ardă. Merge la canalele numai cu sunet, la pauză și la posturile de radio fără ecranul radio. Prima tastă închide protecția și nu face altceva."),
}

# tastele colorate de pe ecranul radio (Screens/HdsEcranRadio.py) si butoanele paginii web: care setare trece la
# alegerea urmatoare si cum se numeste pe ecran („Vizualizarea: Cerc”)
TASTE_ALEGERI = ("vizualizator", "culori")
TITLURI_ALEGERE = {
	"vizualizator": N_("Vizualizarea: %s"),
	"culori": N_("Culorile: %s"),
}


def urmatoarea(nume, valoare=None):
	"""Alegerea de dupa `valoare` (implicit cea de acum) a setarii `nume` („vizualizator”, „culori”), in ordinea de
	pe ecran, cu intoarcere la inceput dupa ultima."""
	valori = [v for v, t in ALEGERI[nume]]
	if valoare is None:
		valoare = valoare_setare(nume)
	try:
		i = valori.index(valoare)
	except ValueError:
		return valori[0]
	return valori[(i + 1) % len(valori)]


def text_alegere(nume, valoare):
	"""Numele alegerii `valoare` a setarii `nume`, netradus (se traduce la folosire)."""
	for v, t in ALEGERI.get(nume, ()):
		if v == valoare:
			return t
	return valoare


_VIZIBIL = [False, False]


def ecran_radio_vizibil():
	"""True cat fereastra radio e aratata pe televizor (si pe un canal numai cu sunet)."""
	return _VIZIBIL[0]


def ecran_numai_sunet():
	"""True cat fereastra radio e aratata pe un canal TV care trimite numai sunet."""
	return _VIZIBIL[0] and _VIZIBIL[1]


def pune_vizibil(da, numai_sunet=False):
	_VIZIBIL[0] = bool(da)
	_VIZIBIL[1] = bool(da) and bool(numai_sunet)


def initProtectie(config=None):
	"""Setarile OE-Alliance ale protectiei ecranului (config.usage.screenSaverStartTimer, screenSaverMoveTimer,
	screenSaverMode), cu aceleasi nume si valori ca in enigma2 OE-Alliance, ca pluginurile sa le gaseasca. Puse o
	singura data (UsageConfig si initConfig); ce exista deja nu se atinge."""
	if config is None:
		from Components.config import config
	from Components.config import ConfigSelection, ConfigSubsection
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	u = config.usage
	if "screenSaverStartTimer" not in u.content.items:
		u.screenSaverStartTimer = ConfigSelection(default=PROTECTIE_IMPLICIT,
			choices=[(v, _tr(t)) for v, t in PROTECTIE])
	if "screenSaverMoveTimer" not in u.content.items:
		u.screenSaverMoveTimer = ConfigSelection(default=10,
			choices=[(x, _tr(N_("%d secunde")) % x) for x in range(5, 61, 5)])
	if "screenSaverMode" not in u.content.items:
		u.screenSaverMode = ConfigSelection(default=PROTECTIE_FEL_ALES, choices=[(v, _tr(t)) for v, t in PROTECTIE_FEL])
	return u


def element(nume, c=None):
	"""Elementul de config al randului `nume`: din config.hds_radio sau, pentru randurile din EXTERNE, din alta sectiune
	(protectia ecranului e config.usage.screenSaverStartTimer, numele OE-Alliance)."""
	if c is None:
		c = initConfig()
	if nume in EXTERNE:
		sectiune, cheie = EXTERNE[nume]
		radacina = _RADACINA[0]
		if radacina is None:
			from Components.config import config as radacina
		initProtectie(radacina)
		return getattr(getattr(radacina, sectiune), cheie)
	return getattr(c, nume)


# radacina config-ului folosita de initConfig (probele de pe PC dau alta decat Components.config.config)
_RADACINA = [None]


def initConfig(config=None):
	"""config.hds_radio; se poate chema de oricate ori. `config` il dau probele de pe PC."""
	if config is None:
		from Components.config import config
	_RADACINA[0] = config
	if "hds_radio" in config.content.items:
		return config.hds_radio
	from Components.config import ConfigSubsection, ConfigSelection, ConfigYesNo
	c = ConfigSubsection()
	config.hds_radio = c
	initProtectie(config)
	for nume in ORDINE:
		if nume in EXTERNE:
			continue
		if nume in DA_NU:
			setattr(c, nume, ConfigYesNo(default=IMPLICITE[nume]))
		else:
			alegeri = [(v, _tr(t)) for v, t in ALEGERI[nume]]
			setattr(c, nume, ConfigSelection(choices=alegeri, default=IMPLICITE[nume]))
	return c


def _tr(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def valoare(nume):
	"""Valoarea unei setari (cu implicitul, daca setarile nu se pot citi)."""
	try:
		return element(nume).value
	except Exception:
		return IMPLICITE[nume]


valoare_setare = valoare


def ecran_pornit():
	return bool(valoare("ecran"))


def numar_cadre():
	try:
		return max(5, min(30, int(valoare("cadre"))))
	except (TypeError, ValueError):
		return 20


def numar_bare():
	try:
		n = int(valoare("bare"))
	except (TypeError, ValueError):
		n = 24
	return n if n in (12, 16, 24) else 24


def minute_odihna():
	"""0 = niciodata."""
	try:
		return max(0, int(valoare("odihna")))
	except (TypeError, ValueError):
		return 10


def numar_epg():
	try:
		return max(1, min(4, int(valoare("epg"))))
	except (TypeError, ValueError):
		return 3


def numai_sunet_radio():
	"""Pe un canal numai cu sunet se arata ecranul radio (alegerea „Ecranul radio” sau „amandoua”)."""
	return valoare("numai_sunet") in ("radio", "amandoua")


def numai_sunet_protectie():
	"""Pe un canal numai cu sunet porneste protectia ecranului (alegerea „Protectia ecranului” sau „amandoua”)."""
	return valoare("numai_sunet") in ("protectie", "amandoua")


def secunde_protectie():
	"""Dupa cate secunde fara taste porneste protectia ecranului; 0 = niciodata."""
	try:
		return max(0, int(valoare("protectie")))
	except (TypeError, ValueError):
		return PROTECTIE_IMPLICIT
