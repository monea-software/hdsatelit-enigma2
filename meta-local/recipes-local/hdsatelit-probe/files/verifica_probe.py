# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# verifica_probe.py: paza retetei hdsatelit-probe, la do_install (nu se instaleaza pe receptor). Datele instalate
# trebuie sa fie bune, altfel constructia se opreste: index.json e JSON valid, al probelor (fel, v, api), cu versiunea
# retetei (PV); fiecare proba din index are fisierul ei cu suma sha256 din index si forma ceruta (PROBA cu numele din
# index, TEXTE cu titlu, def ruleaza); cu --cu-semnatura, index.json.sig exista si are forma semnaturii HD Satelit
# (antetul si scopul hdsatelit-probe). Semnatura insasi o verifica fa_pachet_probe.py (cu inelul imaginii) si
# receptorul (Components/HdsProbe.incarcaSet). Folosire: python3 verifica_probe.py <dosarul instalat> <PV> [--cu-semnatura]
import ast
import hashlib
import json
import os
import re
import sys

_NUME = re.compile(r"\A[a-z][a-z0-9_]{0,23}\Z")


def _forma(cod, nume):
	"""Motivul pentru care fisierul nu e o proba, sau None."""
	try:
		arbore = ast.parse(cod.decode("utf-8"))
	except (SyntaxError, UnicodeDecodeError) as e:
		return "nu e Python: %s" % e
	proba = texte = ruleaza = None
	for n in arbore.body:
		if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
			if n.targets[0].id == "PROBA":
				proba = n.value
			elif n.targets[0].id == "TEXTE":
				texte = n.value
		elif isinstance(n, ast.FunctionDef) and n.name == "ruleaza":
			ruleaza = n
	if not isinstance(proba, ast.Dict) or ruleaza is None or not isinstance(texte, ast.Dict):
		return "fara PROBA, TEXTE sau ruleaza"
	d = dict((k.value, v) for k, v in zip(proba.keys, proba.values) if isinstance(k, ast.Constant))
	if not isinstance(d.get("nume"), ast.Constant) or d["nume"].value != nume:
		return "PROBA nu are numele %s" % nume
	if "titlu" not in [k.value for k in texte.keys if isinstance(k, ast.Constant)]:
		return "TEXTE fara titlu"
	return None


def verifica(d, pv, cere_semnatura=False):
	try:
		with open(os.path.join(d, "index.json"), "rb") as f:
			idx = json.loads(f.read().decode("utf-8"))
	except (OSError, IOError, ValueError, UnicodeDecodeError) as e:
		return "index.json: %s" % e
	if not isinstance(idx, dict) or idx.get("fel") != "hds-probe" or idx.get("v") != 1 or idx.get("api") != 1:
		return "index.json nu e al probelor (fel, v, api)"
	if idx.get("versiune") != pv:
		return "versiunea din index.json (%s) nu e PV (%s)" % (idx.get("versiune"), pv)
	probe = idx.get("probe")
	if not isinstance(probe, list) or not probe:
		return "index.json fara probe"
	for e in probe:
		nume, fisier, sha = e.get("nume"), e.get("fisier"), e.get("sha256")
		if not (isinstance(nume, str) and _NUME.match(nume) and fisier == nume + ".py"):
			return "intrarea %r" % (e,)
		try:
			with open(os.path.join(d, fisier), "rb") as f:
				cod = f.read()
		except (OSError, IOError):
			return "lipseste %s" % fisier
		if hashlib.sha256(cod).hexdigest() != sha:
			return "%s nu are suma din index.json" % fisier
		g = _forma(cod, nume)
		if g:
			return "%s: %s" % (fisier, g)
	if cere_semnatura:
		try:
			with open(os.path.join(d, "index.json.sig"), "rb") as f:
				randuri = f.read().decode("ascii").splitlines()
		except (OSError, IOError, UnicodeDecodeError):
			return "lipseste semnatura (index.json.sig): py -3.12 fa_pachet_probe.py pachet --semneaza"
		if not randuri or randuri[0].strip() != "hdsatelit-semnatura 1 hdsatelit-probe" or len(randuri) < 2 or \
				not all(r.startswith("ed25519 ") for r in randuri[1:] if r.strip()):
			return "semnatura (index.json.sig) nu are forma buna"
	return None


if __name__ == "__main__":
	greseala = verifica(sys.argv[1], sys.argv[2], "--cu-semnatura" in sys.argv[3:])
	if greseala:
		print("hdsatelit-probe: %s" % greseala)
		sys.exit(1)
	print("hdsatelit-probe: datele sunt bune")
