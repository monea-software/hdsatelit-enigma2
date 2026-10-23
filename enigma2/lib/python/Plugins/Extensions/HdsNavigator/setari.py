# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# setari.py: setarile navigatorului web (config.plugins.hdsnavigator), favoritele si dosarele profilului.
#
# O singura logica pentru televizor (ecrane.HdsNavigatorSetari) si pentru interfata web (navigator_web.py): alegerile
# setarilor, citirea si scrierea favoritelor, stergerea datelor de navigare.
#
# Discul: favoritele se scriu numai la o schimbare (un fisier mic, JSON, mutat peste cel vechi); profilul navigatorului
# (cookie-uri, date ale siturilor, mariri tinute minte) sta in DOSAR_DATE, iar cache-ul in memorie (DOSAR_CACHE, pe
# /tmp), ca navigarea sa nu scrie des pe eMMC. In modul „interfata camului” navigatorul nu scrie nimic pe disc.
#
# hbbtv_semn: semnul rosu HbbTV din bara de informatii (Components/HdsHbbtv.semn_rosu_pornit), aici fiindca aplicatiile
# HbbTV ruleaza in acelasi navigator; pornit din fabrica.
# chenar: chenarul care pulseaza pe elementul ales in pagina, desenat de lansator peste pagina (--chenar); pornit din
# fabrica. hbbtv_semn e si in pagina web /navigator, cu "Șterge datele HbbTV" (stergeDateleHbbtv:
# cookie-urile si datele aplicatiilor HbbTV, separate de ale navigatorului obisnuit).
# Stilul chenarului (din 0.2.7: culoarea si forma alese de om din setarile navigatorului):
# chenar_culoare, chenar_forma, chenar_grosime, chenar_puls (Da/Nu) si chenar_viteza, pe televizor sub "Chenarul pe
# selecție" (ascunse cand chenarul e oprit; viteza numai cu pulsul pornit), in pagina web /navigator si in Caută
# setări. Valorile sunt chiar cuvintele lansatorului (lansator.stilChenar); cele din fabrica dau chenarul de dinainte.
# Chenarul si stilul lui sunt acum si in pagina web /navigator; schimbate cat navigatorul e deschis, se vad pe loc.
# hbbtv (0.2.8): setarea principala "HbbTV", OPRITA din fabrica; oprita, nimic HbbTV nu
# mai porneste si nucleul nu mai citeste AIT-ul (Components/HdsHbbtv.hbbtv_pornit); pe televizor primul rand din
# partea HbbTV (cu ea oprita semnul rosu si pornirea automata nu se mai vad), in /navigator si in Caută setări.
# hbbtv_autostart (0.2.8 a planului HbbTV): "Pornirea automată a aplicațiilor HbbTV", oprita din fabrica; cu ea
# aplicatia AUTOSTART a canalului porneste singura, ascunsa, iar ROSU o arata (Components/HdsHbbtvPornire.py); pe
# televizor sub "Semnul roșu HbbTV în bară", in pagina web /navigator (cardul HbbTV) si in Caută setări.
# hbbtv_clar: "HbbTV clar", oprita din fabrica. Oprita, aplicatia HbbTV se deseneaza la 1280x720 si o mareste
# lansatorul la copiere (--marire-la-copiere, lansator.HBBTV_MARIRE_LA_COPIERE), ca tastele sa raspunda repede;
# pornita, WebKit deseneaza la marimea intreaga a ecranului (mai clar, tastele cu 30-50 % mai lente, masurat).
# Se foloseste la urmatoarea pornire a aplicatiei (Components/HdsHbbtvPornire._porneste). Pe televizor sub pornirea
# automata (numai cu HbbTV pornit), in pagina web /navigator (cardul HbbTV) si in Caută setări.
#
# Modulul nu importa enigma2 la incarcare: probele de pe PC dau setarile lor.

import json
import os
import re
import shutil

# pagina de pornire din fabrica (si cea folosita cand adresa salvata nu e buna); webul /navigator ia aceeasi constanta
PAGINA_IMPLICITA = "https://www.hdsatelit.com/"
DOSAR_DATE = "/home/root/.local/share/hds-navigator"
DOSAR_CACHE = "/tmp/hds-navigator-cache"
# datele aplicatiilor HbbTV (Components/HdsHbbtvPornire.DOSAR_DATE si DOSAR_CACHE), ale utilizatorului hdsnav
DOSARE_HBBTV = ("/var/lib/hds-navigator/hbbtv", "/tmp/hds-hbbtv-cache")
FISIER_FAVORITE = "/etc/enigma2/hdsnavigator-favorite.json"
FAVORITE_MAXIM = 100
ADRESA_MAXIMA = 2048
# cautarea pentru ce scrie omul in bara de adrese si nu e o adresa (un cuvant fara punct, cuvinte cu spatiu): Google
CAUTARE = "https://www.google.com/search?q="
TITLU_MAXIM = 200

MARIRI = ("auto", "100", "125", "150", "175", "200")
FONTURI = ("0", "12", "14", "16", "18", "20")
DESENE = ("auto", "procesor")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


ETICHETE = {
	"pagina_pornire": N_("Pagina de pornire"),
	"marire": N_("Mărirea paginii"),
	"font_minim": N_("Mărimea minimă a literelor"),
	"desen": N_("Desenul paginii"),
	"hbbtv": N_("HbbTV (aplicațiile canalelor)"),
	"hbbtv_semn": N_("Semnul roșu HbbTV în bară"),
	"hbbtv_autostart": N_("Pornirea automată a aplicațiilor HbbTV"),
	"hbbtv_clar": N_("HbbTV clar"),
	"chenar": N_("Chenarul pe selecție"),
	"chenar_culoare": N_("Culoarea chenarului"),
	"chenar_forma": N_("Forma chenarului"),
	"chenar_grosime": N_("Grosimea chenarului"),
	"chenar_puls": N_("Chenarul pulsează"),
	"chenar_viteza": N_("Viteza pulsului"),
	"sterge_hbbtv": N_("Șterge datele HbbTV"),
}

DESCRIERI = {
	"pagina_pornire": N_("Pagina care se deschide când pornești navigatorul din meniu. Un cuvânt fără punct deschide căutarea Google."),
	"marire": N_("Automată: pagina mai lată decât ecranul se micșorează până încape. Galben, în navigator, mărește pagina și ține minte mărirea pe fiecare site."),
	"font_minim": N_("Literele mai mici decât atât se măresc, ca textul să se citească de la distanță (puncte CSS)."),
	"desen": N_("Automat: placa video, apoi procesorul, dacă placa video nu merge. Numai procesorul: mai încet, dar merge pe orice receptor."),
	"hbbtv": N_("Nu: HbbTV se oprește de tot. Fără semnul roșu, ROȘU și Portal nu mai pornesc aplicațiile canalelor, iar receptorul nu mai citește tabela lor. Navigatorul web rămâne."),
	"hbbtv_semn": N_("Pe canalele cu aplicație HbbTV, bara de informații arată semnul HbbTV pe roșu. Apasă ROȘU ca să pornești aplicația."),
	"hbbtv_autostart": N_("Da: pe canalele cu HbbTV, aplicația canalului pornește singură, ascunsă, iar ROȘU o arată pe loc. Ține memorie ocupată cât privești canalul și nu pornește în timpul unei înregistrări, în timeshift sau cu memorie puțină. Nu: aplicația pornește numai la ROȘU."),
	"hbbtv_clar": N_("Da: aplicațiile HbbTV se desenează la mărimea întreagă a ecranului, deci textul și pozele sunt mai clare, dar tastele răspund mai încet. Nu: aplicația se desenează mai mic și se mărește, iar tastele răspund repede. Se folosește de la următoarea pornire a aplicației."),
	"chenar": N_("Un chenar arată elementul ales în pagină, chiar dacă site-ul îl ascunde. Culoarea, forma, grosimea și pulsul lui se aleg mai jos."),
	"chenar_culoare": N_("Contrast automat: galben pe paginile închise și albastru închis pe cele deschise, după cum arată pagina sub chenar."),
	"chenar_forma": N_("Dreptunghi: chenarul obișnuit. Colțuri rotunjite: același chenar, cu colțurile rotunde. Subliniere: o linie sub element. Fundal colorat: elementul se colorează ușor."),
	"chenar_grosime": N_("Cât de gros este chenarul. La fundalul colorat: cât de tare se vede culoarea."),
	"chenar_puls": N_("Da: chenarul se luminează și se întunecă mereu, ca să se vadă ușor. Nu: chenarul are mereu aceeași culoare."),
	"chenar_viteza": N_("Lentă: un puls la două secunde. Normală: unul pe secundă. Rapidă: două pe secundă."),
	"sterge_hbbtv": N_("OK: șterge cookie-urile și datele salvate de aplicațiile HbbTV ale canalelor (de exemplu alegerea din fereastra de consimțământ)."),
}


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def alegeriMarire():
	return [("auto", _t("Automată"))] + [(v, "%s %%" % v) for v in MARIRI[1:]]


def alegeriFont():
	return [("0", _t("Fără"))] + [(v, v) for v in FONTURI[1:]]


def alegeriDesen():
	return [("auto", _t("Automat")), ("procesor", _t("Numai procesorul"))]


# Stilul chenarului: (valoarea = cuvantul lansatorului, textul de pe ecran), in ordinea de pe ecran.
CULORI_CHENAR = (
	("galben", N_("Galben")),
	("alb", N_("Alb")),
	("verde", N_("Verde")),
	("albastru", N_("Albastru deschis")),
	("portocaliu", N_("Portocaliu")),
	("rosu", N_("Roșu")),
	("auto", N_("Contrast automat")),
)
FORME_CHENAR = (
	("dreptunghi", N_("Dreptunghi")),
	("rotunjit", N_("Colțuri rotunjite")),
	("subliniere", N_("Subliniere")),
	("fundal", N_("Fundal colorat")),
)
GROSIMI_CHENAR = (("subtire", N_("Subțire")), ("normal", N_("Normală")), ("gros", N_("Groasă")))
VITEZE_PULS = (("lent", N_("Lentă")), ("normal", N_("Normală")), ("rapid", N_("Rapidă")))
# randurile stilului, in ordinea de pe ecran (sub "Chenarul pe selecție"), si valorile din fabrica (chenarul de dinainte)
CHEI_STIL = ("chenar_culoare", "chenar_forma", "chenar_grosime", "chenar_puls", "chenar_viteza")
STIL_FABRICA = {"chenar_culoare": "galben", "chenar_forma": "dreptunghi", "chenar_grosime": "normal", "chenar_puls": True,
	"chenar_viteza": "normal"}


def alegeriDin(tabel):
	"""Alegerile unei setari din tabelul ei, traduse."""
	return [(v, _t(t)) for v, t in tabel]


def randuriHbbtv(c):
	"""Randurile HbbTV care se vad acum: semnul rosu, pornirea automata si HbbTV clar numai cu HbbTV pornit."""
	return ["hbbtv_semn", "hbbtv_autostart", "hbbtv_clar"] if c.hbbtv.value else []


def randuriChenar(c):
	"""Cheile randurilor stilului care se vad acum: niciunul cu chenarul oprit, viteza numai cu pulsul pornit."""
	if not c.chenar.value:
		return []
	return [k for k in CHEI_STIL if k != "chenar_viteza" or c.chenar_puls.value]


def setariChenar(c):
	"""Chenarul si stilul lui pentru lansator (lansator.stilChenar)."""
	return {"chenar": bool(c.chenar.value), "chenar_culoare": c.chenar_culoare.value, "chenar_forma": c.chenar_forma.value,
		"chenar_grosime": c.chenar_grosime.value, "chenar_puls": bool(c.chenar_puls.value),
		"chenar_viteza": c.chenar_viteza.value}


_config = [None]


def initConfig(config=None):
	"""config.plugins.hdsnavigator, creat o singura data (si la probe, cu config-ul lor)."""
	if _config[0] is not None:
		return _config[0]
	from Components.config import ConfigSelection, ConfigSubsection, ConfigText, ConfigYesNo
	if config is None:
		from Components.config import config
	c = ConfigSubsection()
	c.pagina_pornire = ConfigText(default=PAGINA_IMPLICITA, fixed_size=False)
	c.marire = ConfigSelection(choices=alegeriMarire(), default="auto")
	c.font_minim = ConfigSelection(choices=alegeriFont(), default="14")
	c.desen = ConfigSelection(choices=alegeriDesen(), default="auto")
	c.hbbtv = ConfigYesNo(default=False)
	c.hbbtv_semn = ConfigYesNo(default=True)
	c.hbbtv_autostart = ConfigYesNo(default=False)
	c.hbbtv_clar = ConfigYesNo(default=False)
	c.chenar = ConfigYesNo(default=True)
	f = STIL_FABRICA
	c.chenar_culoare = ConfigSelection(choices=alegeriDin(CULORI_CHENAR), default=f["chenar_culoare"])
	c.chenar_forma = ConfigSelection(choices=alegeriDin(FORME_CHENAR), default=f["chenar_forma"])
	c.chenar_grosime = ConfigSelection(choices=alegeriDin(GROSIMI_CHENAR), default=f["chenar_grosime"])
	c.chenar_puls = ConfigYesNo(default=f["chenar_puls"])
	c.chenar_viteza = ConfigSelection(choices=alegeriDin(VITEZE_PULS), default=f["chenar_viteza"])
	config.plugins.hdsnavigator = c
	_config[0] = c
	return c


def adresaBuna(text):
	"""Adresa scrisa de om, cu http(s):// pus in fata cand lipseste; un cuvant fara punct sau cuvinte cu spatiu merg la
	cautarea Google (CAUTARE); '' pentru ce nu se deschide (alte scheme, semne de control, prea lunga)."""
	text = (text or "").strip()
	if not text or len(text) > ADRESA_MAXIMA or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
		return ""
	low = text.lower()
	if low.startswith("http://") or low.startswith("https://"):
		return text if len(text) > len("https://") else ""
	if "://" in low or low.startswith(("javascript:", "data:", "file:", "about:")):
		return ""
	# o adresa IPv4 sau o gazda cu port: aparat din casa, de obicei fara https
	if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d{1,5})?(/.*)?$", text) or re.match(r"^[^/\s]+:\d{1,5}(/.*)?$", text):
		return "http://" + text
	if " " in text or ("." not in text and not low.startswith("localhost")):
		# un cuvant fara punct: cautare Google
		try:
			from urllib.parse import quote_plus
		except ImportError:  # Python 2 (probe vechi)
			from urllib import quote_plus
		return CAUTARE + quote_plus(text)
	return "https://" + text


# ---------------------------------------------------------------- favorite

def citesteFavorite(cale=None):
	"""[{"adresa", "titlu"}], fara intrarile stricate; [] daca fisierul lipseste sau nu se poate citi."""
	cale = cale or FISIER_FAVORITE
	try:
		with open(cale, "rb") as f:
			date = json.loads(f.read(512 * 1024).decode("utf-8", "replace"))
	except (IOError, OSError, ValueError):
		return []
	rez = []
	for x in date if isinstance(date, list) else []:
		if isinstance(x, dict) and adresaBuna(x.get("adresa")) == x.get("adresa"):
			rez.append({"adresa": x["adresa"], "titlu": str(x.get("titlu") or "")[:TITLU_MAXIM]})
	return rez[:FAVORITE_MAXIM]


def scrieFavorite(lista, cale=None):
	cale = cale or FISIER_FAVORITE
	nou = cale + ".nou"
	with open(nou, "wb") as f:
		f.write(json.dumps(lista[:FAVORITE_MAXIM], ensure_ascii=False, indent=0).encode("utf-8"))
	os.replace(nou, cale)


def adaugaFavorit(adresa, titlu="", cale=None):
	"""(True, mesaj) sau (False, motiv). O adresa deja in lista nu se pune a doua oara."""
	a = adresaBuna(adresa)
	if not a:
		return False, _t("Adresa nu se poate adăuga la favorite.")
	lista = citesteFavorite(cale)
	if any(x["adresa"] == a for x in lista):
		return False, _t("Pagina este deja la favorite.")
	if len(lista) >= FAVORITE_MAXIM:
		return False, _t("Lista de favorite este plină (%d de pagini).") % FAVORITE_MAXIM
	lista.append({"adresa": a, "titlu": (titlu or "").strip()[:TITLU_MAXIM]})
	scrieFavorite(lista, cale)
	return True, _t("Pagina a fost adăugată la favorite.")


def stergeFavorit(index, cale=None):
	lista = citesteFavorite(cale)
	if not 0 <= index < len(lista):
		return False, _t("Pagina nu mai este în favorite.")
	del lista[index]
	scrieFavorite(lista, cale)
	return True, _t("Pagina a fost scoasă din favorite.")


# ---------------------------------------------------------------- datele de navigare

def stergeDatele(dosare=(DOSAR_DATE, DOSAR_CACHE)):
	"""Golire cu navigatorul oprit: cookie-uri, datele siturilor, marirea tinuta minte, cache. Intoarce cati octeti
	s-au sters (aproximativ)."""
	octeti = 0
	for d in dosare:
		if not os.path.isdir(d):
			continue
		for radacina, _dosare, fisiere in os.walk(d):
			for f in fisiere:
				try:
					octeti += os.path.getsize(os.path.join(radacina, f))
				except OSError:
					pass
		shutil.rmtree(d, ignore_errors=True)
	return octeti


def stergeDateleHbbtv():
	"""Cookie-urile si datele aplicatiilor HbbTV (cu aplicatia HbbTV inchisa); dosarele se fac din nou la urmatoarea
	pornire. Intoarce cati octeti s-au sters (aproximativ)."""
	return stergeDatele(DOSARE_HBBTV)
