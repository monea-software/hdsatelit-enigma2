# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# verifica_ajutor.py: paza retetei hdsatelit-ajutor, la do_install (nu se instaleaza pe receptor). Datele instalate
# trebuie sa fie bune, altfel constructia se opreste: index.json e JSON valid, are versiunea retetei (PV), are pagini si
# capitole, iar fiecare pagina sta in fisierul limbii ei (locul si lungimea din index incap in <limba>.dat) si se
# despacheteaza cu dictionarul de la inceputul fisierului; textul de cautare al fiecarei limbi se despacheteaza si are
# cate un rand pe pagina. Folosire: python3 verifica_ajutor.py <dosarul instalat> <PV>
import json
import os
import sys
import zlib


def verifica(d, pv):
	with open(os.path.join(d, "index.json"), "rb") as f:
		idx = json.loads(f.read().decode("utf-8"))
	if idx.get("versiune") != pv:
		return "versiunea din index.json (%s) nu e PV (%s)" % (idx.get("versiune"), pv)
	if not idx.get("pagini") or not idx.get("capitole"):
		return "index.json fara pagini sau capitole"
	for L in idx.get("limbi_text") or []:
		with open(os.path.join(d, "%s.dat" % L), "rb") as f:
			dat = f.read()
		o, n = (idx.get("dictionar") or {}).get(L) or [0, 0]
		zd = dat[o:o + n]
		for p in idx["pagini"]:
			o, m = p["poz"][L]
			if not (0 <= o and m > 0 and o + m <= len(dat)):
				return "pagina %s (%s) iese din fisier" % (p.get("c"), L)
			z = zlib.decompressobj(zlib.MAX_WBITS, zd) if zd else zlib.decompressobj()
			pg = json.loads((z.decompress(dat[o:o + m]) + z.flush()).decode("utf-8"))
			if not isinstance(pg.get("p"), list):
				return "pagina %s (%s) fara parti" % (p.get("c"), L)
		with open(os.path.join(d, "cauta-%s.dat" % L), "rb") as f:
			randuri = [r for r in zlib.decompress(f.read()).decode("utf-8").split("\n") if r]
		if len(randuri) != len(idx["pagini"]):
			return "cauta-%s.dat are %d randuri, nu %d" % (L, len(randuri), len(idx["pagini"]))
	return None


if __name__ == "__main__":
	greseala = verifica(sys.argv[1], sys.argv[2])
	if greseala:
		print("hdsatelit-ajutor: %s" % greseala)
		sys.exit(1)
	print("hdsatelit-ajutor: datele sunt bune")
