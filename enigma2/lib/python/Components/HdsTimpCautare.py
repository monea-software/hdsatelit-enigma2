# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTimpCautare.py - cat dureaza un transponder la cautarea canalelor pe acest receptor, invatat din cautarile facute.
#
# De ce: timpul ramas al cautarii (Components/ServiceScan.py) se calcula numai din transponderele cautarii de acum, deci
# fiecare cautare incepea cu „se calculează” si nu tinea minte nimic; primul transponder de pe fiecare satelit (cu
# rotirea antenei) nu intra deloc in estimare.
#
# Ce face modulul:
#   - tine minte secundele pe transponder pe fel de cautare: cheia „<fel>:<pozitie>:<mod>”, cu fel = sat / cablu /
#     terestru, pozitia orbitala (zecimi) numai la satelit, mod = retea (cu NIT, transpondere noi) sau simplu;
#   - media se tine ca medie cu uitare (cea mai noua cautare cantareste cel mai mult), plafonata la MASURATORI_MAX
#     masuratori, ca o antena sau un LNB schimbat sa se vada dupa cateva cautari;
#   - estimarea pentru o cheie: masuratorile ei; altfel media celorlalte chei de acelasi fel si mod, apoi de acelasi
#     fel; fara nicio masuratoare, valorile de pornire PORNIRE_S (presupuneri, inlocuite de prima cautare);
#   - timpul rotirii antenei intre doi sateliti vine din viteza invatata a motorului (Components/HdsMotorViteza.py, prin
#     Components/HdsCulegereTotala.secunde_mutare), nu de aici.
# Pastrare: /etc/enigma2/hds-cautare-timpi.json, scris o data la sfarsitul unei treceri a cautarii, in .nou si apoi
# os.replace. La import nu se atinge nimic din enigma.
import json
import os
import time

FISIER = "/etc/enigma2/hds-cautare-timpi.json"
# presupunerile de dinainte de prima cautare masurata (secunde pe transponder: acordul, tabelele PAT/SDT/NIT si
# transponderele fara semnal, care asteapta pana la capatul timpului lor)
PORNIRE_S = {"sat": 6.0, "cablu": 3.0, "terestru": 4.0}
# cat cantareste o masuratoare noua fata de media de pana atunci, cand sunt deja multe
MASURATORI_MAX = 40
SECUNDE_MIN = 0.3
SECUNDE_MAX = 120.0
# cate transpondere „cantaresc” valorile invatate langa cele masurate in cautarea de acum (ServiceScan.py): dupa cateva
# transpondere ritmul cautarii de acum conteaza mai mult
GREUTATE_INVATAT = 2.0
# modelul motorului (potrivirea din mutarile invatate) se ia cel mult o data la atatea secunde: estimarile se cer de
# cateva ori pe secunda, iar mutarile invatate se schimba numai la o sosire
MODEL_VALABIL_S = 30.0


def jurnal(text):
	print("[HdsTimpCautare] %s" % text)


def cheie(fel, pozitie=None, retea=False):
	"""cheia unei cautari: sat:192:retea, cablu:-:simplu"""
	poz = str(int(pozitie)) if fel == "sat" and pozitie is not None else "-"
	return "%s:%s:%s" % (fel, poz, "retea" if retea else "simplu")


class Timpi(object):
	"""secundele pe transponder invatate, pe cheie, pastrate in `fisier`"""

	def __init__(self, fisier=None):
		self.fisier = fisier or FISIER
		self.chei = self._citeste()

	def _citeste(self):
		try:
			with open(self.fisier, encoding="utf-8") as f:
				date = json.load(f)
		except (IOError, OSError):
			return {}
		except Exception as e:
			jurnal("fisierul timpilor cautarii e stricat, il ignor: %r" % (e,))
			return {}
		chei = {}
		for k, v in (date.get("chei") or {}).items():
			try:
				s, n = float(v["s"]), int(v["n"])
			except (TypeError, ValueError, KeyError):
				continue
			if SECUNDE_MIN <= s <= SECUNDE_MAX and n > 0:
				chei[str(k)] = {"s": s, "n": min(n, MASURATORI_MAX)}
		return chei

	def scrie(self):
		nou = self.fisier + ".nou"
		try:
			with open(nou, "w", encoding="utf-8") as f:
				json.dump({"versiune": 1, "chei": self.chei}, f, sort_keys=True)
				f.flush()
				os.fsync(f.fileno())
			os.replace(nou, self.fisier)
			return True
		except Exception as e:
			jurnal("timpii cautarii nu au putut fi scrisi: %r" % (e,))
			try:
				os.remove(nou)
			except OSError:
				pass
			return False

	def estimare(self, k):
		"""(secunde pe transponder, de unde): „masurat” (cheia insasi), „asemanator” (acelasi fel si mod, alt satelit,
		sau acelasi fel), „pornire” (nicio masuratoare)"""
		v = self.chei.get(k)
		if v:
			return v["s"], "masurat"
		fel, _poz, mod = (k.split(":") + ["", "", ""])[:3]
		for potrivire in (lambda c: c.startswith(fel + ":") and c.endswith(":" + mod), lambda c: c.startswith(fel + ":")):
			alese = [v for c, v in self.chei.items() if potrivire(c)]
			n = sum(v["n"] for v in alese)
			if n:
				return sum(v["s"] * v["n"] for v in alese) / n, "asemanator"
		return PORNIRE_S.get(fel, PORNIRE_S["sat"]), "pornire"

	def invata(self, k, secunde):
		"""masuratorile unei treceri pentru cheia `k` (lista de secunde pe transponder); intoarce noua medie sau None.
		Nu scrie pe disc (scrie() o data, la sfarsitul trecerii)."""
		bune = [float(s) for s in secunde if SECUNDE_MIN <= float(s) <= SECUNDE_MAX]
		if not bune:
			return None
		v = self.chei.get(k)
		s, n = (v["s"], v["n"]) if v else (0.0, 0)
		for x in bune:
			n = min(n + 1, MASURATORI_MAX)
			s += (x - s) / n
		self.chei[k] = {"s": round(s, 2), "n": n}
		return self.chei[k]["s"]


_timpi = None


def timpi():
	global _timpi
	if _timpi is None:
		_timpi = Timpi()
	return _timpi


def _culegere():
	try:
		from Components import HdsCulegereTotala as C
	except ImportError:
		import HdsCulegereTotala as C
	return C


_model = [None, 0.0]


def modelMotor():
	"""{t0, viteza} din mutarile invatate ale motorului (sau presupunerile lor), tinut MODEL_VALABIL_S; None la eroare"""
	acum = time.monotonic()
	if _model[0] is None or acum - _model[1] > MODEL_VALABIL_S:
		try:
			C = _culegere()
			_model[0], _model[1] = C.Receptor(None).model_motor(), acum
		except Exception as e:
			jurnal("modelul motorului: %r" % (e,))
			return None
	return _model[0]


def secundeMutare(de_la, la, model=None):
	"""cat ia rotirea antenei intre doua pozitii orbitale (zecimi), dupa viteza invatata a motorului (sau presupunerile
	ei); 0 pe aceeasi pozitie; None daca nu se poate calcula. `model` = modelMotor() luat o data de cel care cheama."""
	if de_la is None or la is None or de_la == la:
		return 0.0
	try:
		model = model or modelMotor()
		if model is None:
			return None
		return float(_culegere().secunde_mutare(de_la, la, model))
	except Exception as e:
		jurnal("durata rotirii: %r" % (e,))
		return None
