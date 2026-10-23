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
# mesajele de ecran negru ale barei) fara sa importe ecranul; il pune numai fereastra radio.


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
	("5", N_("După 5 minute fără taste")),
	("10", N_("După 10 minute fără taste")),
	("15", N_("După 15 minute fără taste")),
	("30", N_("După 30 de minute fără taste")),
	("0", N_("Niciodată")),
)
EPG = (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"))

IMPLICITE = {
	"ecran": True,
	"vizualizator": "varfuri",
	"culori": "skin",
	"bare": "24",
	"cadre": "20",
	"odihna": "10",
	"epg": "3",
	"bara_la_zap": False,
}

ORDINE = ("ecran", "vizualizator", "culori", "bare", "cadre", "odihna", "epg", "bara_la_zap")
DA_NU = ("ecran", "bara_la_zap")
ALEGERI = {
	"vizualizator": VIZUALIZATOARE,
	"culori": CULORI,
	"bare": BARE,
	"cadre": CADRE,
	"odihna": ODIHNA,
	"epg": EPG,
}

ETICHETE = {
	"ecran": N_("Ecranul radio pe tot ecranul"),
	"vizualizator": N_("Vizualizatorul"),
	"culori": N_("Culorile"),
	"bare": N_("Numărul de bare"),
	"cadre": N_("Fluiditatea"),
	"odihna": N_("Ecranul de odihnă"),
	"epg": N_("Emisiunile următoare"),
	"bara_la_zap": N_("Bara la schimbarea postului"),
}

# fraza simpla intai; explicatia tehnica, daca e utila, dupa ea
DESCRIERI = {
	"ecran": N_("Când asculți un post de radio, ecranul arată numele postului, emisiunile, piesa, sunetul și semnalul. Cu Nu rămâne ecranul obișnuit."),
	"vizualizator": N_("Cum se arată muzica pe ecran. Pe ecranul radio, tasta galbenă trece la următoarea. Barele urmăresc sunetul adevărat al postului, pe orice format de sunet."),
	"culori": N_("Culorile barelor. Pe ecranul radio, tasta albastră trece la următoarele. „Culorile ecranelor” folosește aceleași culori ca meniurile receptorului."),
	"bare": N_("Câte bare are vizualizatorul. Fiecare bară arată o parte din frecvențele sunetului. Barele se întind numai pe frecvențele pe care postul le transmite, deci pot fi mai puține."),
	"cadre": N_("De câte ori pe secundă se mișcă barele. Mai puține cadre încarcă mai puțin receptorul."),
	"odihna": N_("După atâtea minute fără nicio tastă rămân pe ecran doar numele postului, piesa și ceasul, care se mută încet, ca ecranul televizorului să nu se ardă. Orice tastă aduce ecranul întreg."),
	"epg": N_("Câte emisiuni următoare se arată sub emisiunea de acum, când postul transmite programul."),
	"bara_la_zap": N_("Cu Da, la schimbarea postului de radio apare și bara obișnuită de jos. Ecranul radio are deja toate datele."),
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


_VIZIBIL = [False]


def ecran_radio_vizibil():
	"""True cat fereastra radio e aratata pe televizor."""
	return _VIZIBIL[0]


def pune_vizibil(da):
	_VIZIBIL[0] = bool(da)


def initConfig(config=None):
	"""config.hds_radio; se poate chema de oricate ori. `config` il dau probele de pe PC."""
	if config is None:
		from Components.config import config
	if "hds_radio" in config.content.items:
		return config.hds_radio
	from Components.config import ConfigSubsection, ConfigSelection, ConfigYesNo
	c = ConfigSubsection()
	config.hds_radio = c
	for nume in ORDINE:
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
		return getattr(initConfig(), nume).value
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
