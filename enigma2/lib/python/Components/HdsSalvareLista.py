# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Salvarea listei: obiecte pe firul principal, numai octeti pe firul de disc."""
import os
import threading
import time

_MEMORIE = [None]
_CITIRE = [False]
_ULTIMA = [0]
_OCUPAT = [False]
_VERSIUNE = [0]
_ZAVOR = threading.RLock()


def memoreaza(cfg):
	_ULTIMA[0] = time.monotonic()
	_VERSIUNE[0] += 1
	_MEMORIE[0] = {k: cfg.get(k, "da") for k in ("activ", "rezerva")}


def _citeste(cale):
	cfg = {"activ": "da", "rezerva": "da"}
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				k, sep, v = rand.partition("=")
				k = k.strip().lower()
				if sep and k in cfg:
					cfg[k] = v.strip().lower()
	except FileNotFoundError:
		pass
	return cfg


def setariMemorie():
	if not _CITIRE[0] and time.monotonic() - _ULTIMA[0] > 10:
		from Components import HdsDvbISetari as S
		from twisted.internet.threads import deferToThread
		_CITIRE[0] = True
		_ULTIMA[0] = time.monotonic()
		versiune = _VERSIUNE[0]
		def gata(cfg):
			_CITIRE[0] = False
			if versiune != _VERSIUNE[0]:
				return
			memoreaza(cfg)
			from Components import HdsDvbIRezerva as R
			from Components.config import config
			el = getattr(config.usage, "hds_dvbi_rezerva", None)
			R.rezervaSchimbata(el.value if el is not None else cfg["rezerva"] in ("da", "yes", "1", "true"))
			if el is not None:
				el.changed()
		def eroare(f):
			_CITIRE[0] = False
			# O eroare trecatoare la pornire nu lasa rezerva oprita definitiv.
			from twisted.internet import reactor
			reactor.callLater(11, setariMemorie)
			return None
		deferToThread(_citeste, S.CALE_CONFIG).addCallbacks(gata, eroare)
	# Fara citirea initiala nu se porneste automat o rezerva posibil oprita de om.
	return dict(_MEMORIE[0] or {"activ": "nu", "rezerva": "da"})


def valoareRezerva():
	return setariMemorie()["rezerva"] in ("da", "yes", "1", "true")


def _octeti(cale):
	try:
		with open(cale, "rb") as f:
			return f.read()
	except FileNotFoundError:
		return None


def scrieVerificat(cale, continut, scrie):
	if not scrie(cale, continut) or _octeti(cale) != continut:
		raise OSError("settings verification failed")


def _disc(cale, text, dvbi, alegere, scrie):
	# Nu primeste config, configfile, elemente, sesiuni sau obiecte enigma.
	from Components.config import _canalDinBaza, _octetiSetari
	with _ZAVOR:
		tinta = os.path.realpath(cale)
		vechi = _octeti(cale)
		# Ca salvarea periodica: ultimul canal sigur ramane cel de pe disc.
		text = _octetiSetari(_canalDinBaza(text.decode("utf-8", "surrogateescape"),
			(vechi or b"").decode("utf-8", "surrogateescape")))
		try:
			scrieVerificat(cale, text, scrie)
			if alegere is not None:
				continut = _octeti(dvbi) or b""
				rand = b"rezerva = " + (b"da" if alegere else b"nu") + b"\n"
				linii = continut.splitlines(keepends=True)
				noi, pus = [], False
				for linie in linii:
					if linie.partition(b"=")[0].strip() == b"rezerva":
						if not pus:
							noi.append(rand)
							pus = True
					else:
						noi.append(linie)
				if not pus:
					if noi and not noi[-1].endswith(b"\n"):
						noi.append(b"\n")
					noi.append(rand)
				nou = b"".join(noi)
				if nou != continut:
					scrieVerificat(dvbi, nou, scrie)
			return _citeste(dvbi)
		except Exception:
			# Nu suprascrie o modificare facuta intre timp de alt scriitor.
			if os.path.realpath(cale) == tinta and _octeti(cale) == text:
				if vechi is None:
					# Sterge numai fisierul creat chiar de operatia nereusita.
					# Daca exista o legatura simbolica, ea ramane neatinsa.
					os.unlink(tinta)
				else:
					scrieVerificat(cale, vechi, scrie)
			raise


def salveaza(randuri, config, configfile, la_gata):
	"""Valideaza si pregateste pe firul principal; rezultatul revine pe acelasi fir."""
	from Components import HdsDvbISetari as S
	from Components.config import _scrieSigur, _octetiSetari, TranzactieSetari
	from twisted.internet.threads import deferToThread
	if _OCUPAT[0]:
		la_gata(False)
		return
	_OCUPAT[0] = True
	vechi = []
	tranzactie = None
	try:
		# Rezerva comuna precede orice valoare marcata ca salvata.
		# Ceilalti scriitori isi pun cererile in coada, fara IO pe firul principal.
		tranzactie = TranzactieSetari()
		from copy import deepcopy
		elemente = list(dict.fromkeys(r[1] for r in randuri if len(r) > 1))
		vechi = [(el, deepcopy(el.saved_value)) for el in elemente]
		rezerva = getattr(config.usage, "hds_dvbi_rezerva", None)
		alegere = rezerva.value if rezerva in elemente and rezerva.isChanged() else None
		pendenta = rezerva._alegere if rezerva is not None else None
		for el in elemente:
			el.save()
		noi = [(el, deepcopy(el.saved_value)) for el in elemente]
		text = config.pickle()
		for el, saved in vechi:
			el.saved_value = saved
		d = deferToThread(tranzactie.ruleaza, _disc, configfile.CONFIG_FILE, _octetiSetari(text), S.CALE_CONFIG, alegere, _scrieSigur)
	except Exception:
		for el, saved in vechi:
			el.saved_value = saved
		if tranzactie is not None:
			tranzactie.inchide(fortat=True)
		_OCUPAT[0] = False
		la_gata(False)
		return
	def termina(ok):
		# Preia fotografia actuala numai pe main, dupa commit sau rollback.
		# Pastreaza rezervarea pana se termina si cererile venite intre timp.
		configfile._scris = None
		try:
			cereri = tranzactie.preia()
			if cereri:
				def esec(f):
					termina(False)
					return None
				deferToThread(tranzactie.termina, cereri).addCallbacks(lambda r: termina(ok), esec)
				return
			if not tranzactie.inchide():
				termina(ok)
				return
		except Exception:
			tranzactie.inchide(fortat=True)
			ok = False
		_OCUPAT[0] = False
		la_gata(ok)
	def gata(cfg):
		for el, saved in noi:
			el.saved_value = saved
		memoreaza(cfg)
		if rezerva is not None and rezerva in elemente and rezerva._alegere == pendenta:
			rezerva._alegere = None
			rezerva.saved_value = None
			try:
				rezerva._anunta()
			except Exception:
				print("[HdsSalvareLista] notificarea setarii nu a reusit")
		termina(True)
	def eroare(f):
		for el, saved in vechi:
			el.saved_value = saved
		termina(False)
		return None
	d.addCallbacks(gata, eroare)
