# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# lucru.py: cautarea si descarcarea, aceleasi pentru ecranul de pe televizor si pentru pagina web.
#
# O singura lucrare deodata (cautare sau descarcare), pe un fir: reteaua nu atinge firul enigma2. Starea (faza, mesajul,
# rezultatele, fisierul salvat) se citeste cu stare() de pe orice fir. Punerea subtitrarii descarcate in lista filmului
# si pornirea ei (Components/HdsSubtitrariFilm.py, HdsPisteLimbi) le face aplica(), chemata pe firul enigma2 (de
# ecranul de pe televizor sau de pagina web, care citesc starea): o singura data pe fisier.
#
# Rezultatele: ale tuturor surselor configurate, in ordinea: potrivite dupa amprenta filmului (OpenSubtitles), limba in
# ordinea preferintelor, cele traduse automat si cele pentru surzi la sfarsit, cele mai descarcate intai; fiecare cu fps-ul
# copiei, cand sursa il da. Pe un canal TV sau la o inregistrare .ts (tv.py) cautarea primeste filmul identificat din
# EPG (ID-ul IMDb), iar aplica() pune subtitrarea in serviciul DVB (tv.incarca), nu in lista filmului.
# Fara nicio sursa configurata: un mesaj care spune ce trebuie scris in setari.

import os
import threading
import time

from . import film as F
from . import limbi as LB
from . import retea
from . import salvare
from .conturi import Conturi
from .surse import EroareSursa, module

MAX_REZULTATE = 80


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


class Lucrare(object):
	def __init__(self, conturi=None, surse=None):
		self.conturi = conturi or Conturi()
		self._surse = surse
		self._lacat = threading.Lock()
		self._stare = {"faza": "gata", "mesaj": "", "eroare": False, "rezultate": [], "film": None, "limbi": [],
			"salvat": None, "aplicat": False, "text": "", "pornit": 0, "verificare": None, "verificare_in_curs": False,
			"fps_salvat": None}
		self._interne = []    # rezultatele cu datele surselor (id-urile lor), in aceeasi ordine

	def surse(self):
		if self._surse is None:
			self._surse = module()
		return self._surse

	def stare(self):
		with self._lacat:
			s = dict(self._stare)
			s["rezultate"] = [dict(r) for r in self._stare["rezultate"]]
		s["in_curs"] = s["faza"] in ("cauta", "descarca")
		return s

	def _pune(self, **campuri):
		with self._lacat:
			self._stare.update(campuri)

	def surseConfigurate(self, date=None):
		date = self.conturi.citeste() if date is None else date
		return [s for s in self.surse() if s.configurat(date)]

	def cauta(self, cale_film, text=None, limbi=None, film=None):
		"""Porneste cautarea (pe fir). -> False daca o lucrare merge deja. `film`: filmul de pe un canal TV sau dintr-o
		inregistrare (tv.py): {"titlu", "an", "imdb", "tmdb"}; atunci `cale_film` e locul unde se salveaza subtitrarea
		(langa inregistrare, sau in dosarul subtitrarilor de pe canale), fara amprenta si fara numele fisierului."""
		with self._lacat:
			if self._stare["faza"] in ("cauta", "descarca"):
				return False
			info = F.informatii(cale_film)
			if film is not None:
				info.update({"release": u"", "titlu": (film.get("titlu") or u"")[:120], "an": u"%s" % (film.get("an") or u""),
					"sezon": None, "episod": None, "imdb": film.get("imdb") or u"", "tmdb": film.get("tmdb") or u"",
					"tv": True})
			if text:
				info["titlu"] = text.strip()[:120]
			self._stare.update({"faza": "cauta", "mesaj": _t("Se caută subtitrări..."), "eroare": False, "rezultate": [],
				"film": info, "limbi": list(limbi or LB.implicite()), "salvat": None, "aplicat": False,
				"text": info["titlu"], "pornit": time.time()})
			self._interne = []
		fir = threading.Thread(target=self._cauta, args=(cale_film,), name="HdsSubtitrariInternet")
		fir.daemon = True
		fir.start()
		return True

	def _cauta(self, cale_film):
		try:
			with self._lacat:
				info = dict(self._stare["film"])
				limbi = list(self._stare["limbi"])
			date = self.conturi.citeste()
			surse = self.surseConfigurate(date)
			if not surse:
				# din 0.3.2 descarcarea e in imagine (nu mai e plugin): setarile sunt la Descărcare subtitrări, in meniu
				# si in interfata web (/descarcare-subtitrari)
				self._pune(faza="gata", eroare=True, mesaj=_t("Nicio sursă nu e pregătită. Scrie cheia sau contul unei "
					"surse (OpenSubtitles, subs.ro, SubDL) la Descărcare subtitrări, în meniu sau în interfața web."))
				return
			amprenta = None
			if any(s.ID == "opensubtitles" for s in surse) and not info.get("tv"):
				amprenta, marime = F.amprenta(cale_film)
			toate = []
			probleme = []
			ceas_spus = False
			for s in surse:
				try:
					toate.extend(s.cauta(info, limbi, date, amprenta))
				except (EroareSursa, retea.EroareRetea) as e:
					if getattr(e, "ceas", False):
						# ceasul receptorului in urma: acelasi text la toate sursele, spus o singura data
						if not ceas_spus:
							probleme.append("%s" % e)
						ceas_spus = True
					else:
						probleme.append("%s: %s" % (s.NUME, e))
				except Exception as e:     # o sursa stricata nu opreste celelalte
					probleme.append("%s: %s" % (s.NUME, e.__class__.__name__))
			ordine = dict((c, i) for i, c in enumerate(limbi))
			# cele traduse automat (OpenSubtitles le spune) la coada limbii lor
			toate.sort(key=lambda r: (0 if r.get("potrivire") else 1, ordine.get(r.get("limba"), 99), 1 if r.get("automata") else 0,
				1 if r.get("surzi") else 0, -(r.get("descarcari") or 0)))
			toate = toate[:MAX_REZULTATE]
			publice = []
			for i, r in enumerate(toate):
				surs = [s for s in surse if s.ID == r["sursa"]]
				publice.append({"index": i, "sursa": surs[0].NUME if surs else r["sursa"], "limba": r.get("limba") or "und",
					"limba_text": LB.nume(r.get("limba")), "nume": r.get("nume") or "", "descarcari": r.get("descarcari"),
					"potrivire": bool(r.get("potrivire")), "surzi": bool(r.get("surzi")), "detalii": r.get("detalii") or "",
					"fps": r.get("fps"), "automata": bool(r.get("automata"))})
			if publice:
				mesaj = _t("%d subtitrări găsite.") % len(publice)
			else:
				mesaj = _t("Nu s-a găsit nicio subtitrare pentru „%s” în limbile alese.") % info.get("titlu")
			if probleme:
				mesaj += " " + " ".join(probleme)
			with self._lacat:
				self._interne = toate
				self._stare.update({"faza": "gata", "rezultate": publice, "mesaj": mesaj, "eroare": not publice})
		except Exception as e:
			self._pune(faza="gata", eroare=True, mesaj=_t("Căutarea nu a mers: %s") % e.__class__.__name__)

	def descarca(self, index):
		"""Porneste descarcarea rezultatului `index` (pe fir). -> False daca nu se poate acum."""
		with self._lacat:
			if self._stare["faza"] in ("cauta", "descarca") or not (0 <= index < len(self._interne)):
				return False
			rezultat = dict(self._interne[index])
			info = dict(self._stare["film"] or {})
			self._stare.update({"faza": "descarca", "mesaj": _t("Se descarcă subtitrarea..."), "eroare": False,
				"salvat": None, "aplicat": False, "fps_salvat": rezultat.get("fps")})
		fir = threading.Thread(target=self._descarca, args=(rezultat, info), name="HdsSubtitrariInternet")
		fir.daemon = True
		fir.start()
		return True

	def _descarca(self, rezultat, info):
		try:
			date = self.conturi.citeste()
			surse = [s for s in self.surse() if s.ID == rezultat["sursa"]]
			if not surse:
				raise EroareSursa(_t("Sursa aceasta nu mai există."))
			octeti, nume, mesaj_sursa = surse[0].descarca(rezultat, date)
			sub, nume_sub = salvare.dinArhiva(octeti, nume, info)
			if info.get("tv"):
				# pe un canal: dosarul subtitrarilor (tv.dosarCanal: discul numai daca e montat) se face la prima descarcare
				try:
					os.makedirs(os.path.dirname(info["cale"]), exist_ok=True)
				except OSError:
					pass
			cale, mesaj = salvare.salveaza(sub, nume_sub, info["cale"], rezultat.get("limba"))
			print("[HdsSubtitrariInternet] subtitrare salvata: %s" % os.path.basename(cale))
			self._pune(faza="gata", eroare=False, salvat=cale, mesaj=(mesaj + (" " + mesaj_sursa if mesaj_sursa else "")))
		except (EroareSursa, retea.EroareRetea, salvare.EroareSalvare) as e:
			self._pune(faza="gata", eroare=True, mesaj=str(e))
		except Exception as e:
			self._pune(faza="gata", eroare=True, mesaj=_t("Descărcarea nu a mers: %s") % e.__class__.__name__)

	def verifica(self):
		"""Porneste „Verifică sursele” pe un fir (aceeasi ca pe televizor); rezultatul vine in stare()["verificare"].
		-> False daca o verificare merge deja."""
		with self._lacat:
			if self._stare["verificare_in_curs"]:
				return False
			self._stare.update({"verificare_in_curs": True, "verificare": None})

		def lucreaza():
			try:
				text = u"\n".join(verificaSurse(self.conturi.citeste(), self.surse()))
			except Exception as e:
				text = _t("Verificarea nu a mers: %s") % e.__class__.__name__
			self._pune(verificare=text, verificare_in_curs=False)
		fir = threading.Thread(target=lucreaza, name="HdsSubtitrariInternet")
		fir.daemon = True
		fir.start()
		return True

	def aplica(self, session=None):
		"""Pe firul enigma2: subtitrarea salvata intra in lista filmului si porneste (tinuta minte pe film). O singura data
		pe fisier. -> True daca a pornit acum."""
		with self._lacat:
			cale = self._stare["salvat"]
			if not cale or self._stare["aplicat"]:
				return False
			self._stare["aplicat"] = True
			tv_film = bool((self._stare["film"] or {}).get("tv"))
			fps = self._stare.get("fps_salvat")
		if tv_film:
			# canal TV sau inregistrare .ts: subtitrarea intra in serviciul DVB (tv.py), pe ceasul lui
			from . import tv
			reusit, mesaj = tv.incarca(session, cale, fps)
			with self._lacat:
				self._stare["mesaj"] = (self._stare["mesaj"] + " " + mesaj).strip()
				if not reusit:
					self._stare["eroare"] = True
			return reusit
		try:
			from Components import HdsSubtitrariFilm as SF
			from Components import HdsPisteLimbi as PL
		except ImportError:
			return False
		reusit, mesaj, numar = SF.adaugaFisier(cale)
		if not reusit:
			self._pune(mesaj=mesaj, eroare=True)
			return False
		tuplu = SF.tupluPentru(numar)
		if tuplu:
			PL.alegeSubtitrareDeMana(session, tuplu)
			with self._lacat:
				self._stare["mesaj"] = self._stare["mesaj"] + " " + _t("A pornit.")
			return True
		return False


def verificaSurse(date, surse):
	"""Pe fir: fiecare sursa incercata cu datele scrise. -> randurile pentru om („subs.ro: merge, ...”)."""
	randuri = []
	for s in surse:
		if not s.configurat(date):
			randuri.append("%s: %s" % (s.NUME, _t("nescrisă")))
			continue
		try:
			randuri.append(s.verifica(date))
		except (EroareSursa, retea.EroareRetea) as e:
			text = str(e)
			randuri.append(text if text.lower().startswith(s.NUME.lower()) else "%s: %s" % (s.NUME, text))
		except Exception as e:
			randuri.append("%s: %s" % (s.NUME, e.__class__.__name__))
	return randuri


_LUCRARE = [None]


def lucrare():
	if _LUCRARE[0] is None:
		_LUCRARE[0] = Lucrare()
	return _LUCRARE[0]


def filmulDeAcum():
	"""Calea filmului redat din fisier, sau None."""
	try:
		import NavigationInstance
		ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
		cale = ref.getPath() if ref is not None else ""
	except Exception:
		return None
	try:
		from Components import HdsSubtitrariFilm as SF
		# un film dintr-un loc din retea redat prin adresa: calea lui virtuala (subtitrarile descarcate stau langa ea)
		return SF.caleLocala(cale) if SF.esteFilm(cale) else None
	except ImportError:
		return cale if cale.startswith("/") else None
