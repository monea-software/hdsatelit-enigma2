# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTastaturaUsb.py: tastatura pusa direct in receptor (USB, receptorul unei tastaturi fara fir, Bluetooth).
# lib/driver/rcinput.cpp o recunoaste dupa nume ("keyboard") sau dupa taste (A, Z si Spatiu) si nu o ia exclusiv, deci
# literele si cifrele ajung ca text prin consola (/dev/tty0, cu harta de taste a consolei) acolo unde se scrie: ecranele
# de setari (ConfigList), cautarile, caseta de text si tastatura de pe ecran (kmAscii). Tastele care nu sunt pe
# telecomanda primesc sensul lor de pe telecomanda in eRCMapper (lib/driver/rcmapper.cpp, keyboardDefault), iar
# tastele care sunt si pe telecomanda (sagetile, cifrele, volumul, Mute ...) merg ca de pe telecomanda. Asezarea de mai
# jos (ASEZARE) e aceeasi cu tabelul din C++ (teste/test_mouse_usb.py le compara).
#
# Tastatura de pe ecran (Screens/VirtualKeyBoard.py) nu-si mai arata tastele cand e deschisa de la tastatura sau cand
# se scrie in ea cu tastatura: ramane numai campul de text (Enter = gata, Esc = renunta, Backspace = sterge). O sageata
# de pe telecomanda aduce tastele inapoi. Enter pe un camp de text din setari nu mai deschide tastatura de pe ecran:
# textul se scrie direct in camp (Components/ConfigList.py).

# codurile Linux (linux/input.h)
KEY_ESC, KEY_BACKSPACE, KEY_ENTER, KEY_SPACE, KEY_KPENTER, KEY_COMPOSE = 1, 14, 28, 57, 96, 127
KEY_F1, KEY_F2, KEY_F3, KEY_F4, KEY_F5, KEY_F6, KEY_F7 = 59, 60, 61, 62, 63, 64, 65
KEY_KPMINUS, KEY_KPPLUS = 74, 78
KEY_KP = {82: 11, 79: 2, 80: 3, 81: 4, 75: 5, 76: 6, 77: 7, 71: 8, 72: 9, 73: 10}   # KP0..KP9 -> KEY_0..KEY_9
KEY_OK, KEY_EXIT, KEY_MENU, KEY_INFO, KEY_EPG = 352, 174, 139, 358, 365
KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE = 398, 399, 400, 401
KEY_VOLUMEUP, KEY_VOLUMEDOWN = 115, 114

# (tasta de pe tastatura, tasta telecomenzii; cand se scrie text, tasta telecomenzii sau None = ramane a tastaturii)
ASEZARE = (
	(KEY_ENTER, KEY_OK, KEY_OK),
	(KEY_KPENTER, KEY_OK, KEY_OK),
	(KEY_ESC, KEY_EXIT, KEY_EXIT),
	(KEY_BACKSPACE, KEY_EXIT, None),        # cand se scrie text, Backspace sterge
	(KEY_SPACE, KEY_OK, None),              # cand se scrie text, Spatiu e un spatiu
	(KEY_F1, KEY_RED, KEY_RED),
	(KEY_F2, KEY_GREEN, KEY_GREEN),
	(KEY_F3, KEY_YELLOW, KEY_YELLOW),
	(KEY_F4, KEY_BLUE, KEY_BLUE),
	(KEY_F5, KEY_MENU, KEY_MENU),
	(KEY_COMPOSE, KEY_MENU, KEY_MENU),      # tasta de meniu de langa Ctrl-ul din dreapta
	(KEY_F6, KEY_INFO, KEY_INFO),
	(KEY_F7, KEY_EPG, KEY_EPG),
	(KEY_KPPLUS, KEY_VOLUMEUP, None),
	(KEY_KPMINUS, KEY_VOLUMEDOWN, None),
) + tuple((kp, cifra, None) for kp, cifra in sorted(KEY_KP.items()))


def sens(cod, scrieText=False):
	"""Tasta telecomenzii pentru o tasta de tastatura care nu e pe telecomanda (sau None), ca keyboardDefault din C++."""
	for tasta, telecomanda, laText in ASEZARE:
		if tasta == cod:
			return laText if scrieText else telecomanda
	return None


def dinTastatura():
	"""Ultima tasta apasata (sau ultimul caracter) a venit de la o tastatura (eRCMapper.lastKeyFromKeyboard). False
	pentru telecomanda, panou, pagina web, mouse si cu un binar enigma2 mai vechi."""
	try:
		from enigma import eRCMapper
		m = eRCMapper.getInstance()
		return bool(m is not None and hasattr(m, "lastKeyFromKeyboard") and m.lastKeyFromKeyboard())
	except Exception:
		return False
