# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCursorLista.py - randurile unei liste puse din nou fara ca cursorul sa sara pe primul rand.
#
# La sursa List (Components/Sources/List.py) fiecare setList ajunge in Renderer/Listbox.changed, care pune continutul
# din nou in eListbox (setContent -> entryReset cu cursorul acasa, lib/gui/elistbox.cpp): cursorul trece pe primul rand.
# Ecranele de setari care isi refac randurile dupa o schimbare (STANGA, DREAPTA, OK) le pun prin pune_randurile, iar
# cursorul ramane unde era:
#   - pe randul cu aceeasi cheie (randurile pot aparea sau disparea, deci nu ajunge numarul randului);
#   - daca randul nu mai e in lista, pe cel mai apropiat vecin al lui care a ramas (intai cel de dedesubt);
#   - altfel pe acelasi numar de rand, cel mult ultimul.
# Merge la fel cu MenuList (moveToIndex) si ConfigList (setCurrentIndex), care singure pastreaza numai numarul randului.
#
# Purtarea sursei List nu se schimba: alte ecrane (de pilda lista de canale la schimbarea dosarului) se bazeaza pe
# intoarcerea la primul rand. Fara enigma aici, ca sa se poata proba pe PC.


def cheie_implicita(rand):
	"""A doua valoare a randului (eticheta, cheie, ...), ca la scanere si la ecranele de setari HD Satelit; un rand cu
	o singura valoare are cheia ei, iar un rand care nu e tuplu e propria lui cheie."""
	if isinstance(rand, (tuple, list)):
		if len(rand) > 1:
			return rand[1]
		return rand[0] if rand else None
	return rand


def _functia_cheii(cheie):
	"""cheie: None (cheie_implicita), o functie rand -> cheie sau pozitia cheii in tuplu."""
	if cheie is None:
		return cheie_implicita
	if callable(cheie):
		return cheie
	return lambda rand, pozitie=cheie: rand[pozitie]


def _cheia(f, rand):
	try:
		return f(rand)
	except Exception:
		return None


def _cea_mai_apropiata(chei, cheie, index):
	"""Pozitia din chei egala cu cheie, cea mai apropiata de index (cheile pot fi la mai multe randuri); None daca
	nu e."""
	if cheie is None:
		return None
	pozitii = [i for i, c in enumerate(chei) if c is not None and c == cheie]
	if not pozitii:
		return None
	return min(pozitii, key=lambda i: (abs(i - index), i))


def pozitia_noua(vechi, noi, index, cheie=None):
	"""Randul din noi pe care trebuie sa stea cursorul care era pe randul index din vechi. None cand nu e nimic de
	pus: lista noua e goala sau cursorul nu se stie (lista fara fereastra inca)."""
	if not noi or index is None:
		return None
	try:
		index = int(index)
	except (TypeError, ValueError):
		return None
	if index < 0:
		index = 0
	f = _functia_cheii(cheie)
	chei_noi = [_cheia(f, r) for r in noi]
	vechi = list(vechi or [])
	if index < len(vechi):
		chei_vechi = [_cheia(f, r) for r in vechi]
		gasit = _cea_mai_apropiata(chei_noi, chei_vechi[index], index)
		if gasit is not None:
			return gasit
		# randul nu mai e: vecinii lui, din ce in ce mai departe, intai cel de dedesubt
		for pas in range(1, len(vechi)):
			for j in (index + pas, index - pas):
				if 0 <= j < len(vechi):
					gasit = _cea_mai_apropiata(chei_noi, chei_vechi[j], index)
					if gasit is not None:
						return gasit
	return min(index, len(noi) - 1)


def _index_curent(lista):
	"""Randul cursorului: sursa List (getIndex, None fara fereastra), MenuList (getSelectionIndex), ConfigList
	(getCurrentIndex)."""
	for nume in ("getIndex", "getSelectionIndex", "getCurrentIndex"):
		f = getattr(lista, nume, None)
		if f is not None:
			try:
				return f()
			except Exception:
				return None
	return None


def _pune_index(lista, index):
	for nume in ("setIndex", "moveToIndex", "setCurrentIndex"):
		f = getattr(lista, nume, None)
		if f is not None:
			f(index)
			return


def pune_randurile(lista, randuri, cheie=None):
	"""Pune randuri in lista (sursa List, MenuList sau ConfigList) si lasa cursorul pe randul pe care era (vezi
	pozitia_noua). randuri trebuie sa fie o lista noua, nu cea veche schimbata pe loc: din cea veche se afla cheia
	randului de sub cursor. Intoarce randul pus, sau None cand nu s-a pus niciunul."""
	vechi = getattr(lista, "list", None)
	vechi = list(vechi) if (vechi is not None and vechi is not randuri) else []
	index = _index_curent(lista)
	lista.setList(randuri)
	nou = pozitia_noua(vechi, randuri, index, cheie)
	if nou is not None:
		_pune_index(lista, nou)
	return nou
