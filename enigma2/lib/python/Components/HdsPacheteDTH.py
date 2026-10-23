# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pachetele de satelit predefinite (DTH) pentru utilizatorul din Romania.

De unde vin datele: inainte ele stateau in Screens/ScanSetup.py, in alegerea
"Pachet Operator Satelit (DTH)" (scan_type == "provider_dth"). Ecranul acela nu mai arata randul
"Tip de scanare" pe satelit, deci alegerea ramasese fara niciun drum spre ea si pachetele nu se mai
puteau scana. Datele s-au mutat aici, langa restul componentelor noastre, ca sa nu mai atarne de un
ecran vechi, iar scanarea lor se face din Screens/ScanerSatelit.py ("Ce se cauta" -> "Pachet").

O reparatie mai veche se pastreaza intreaga si este singurul motiv pentru care unitatile sunt
scrise explicit mai jos:
  1. inversarea de spectru (inversion) are locul ei; lipsea, si toate valorile de dupa FEC se decalau
     cu o pozitie. Aici e camp cu nume, deci nu se mai poate decala.
  2. frecventa se scrie in MHz si symbol rate-ul in kSymb/s, asa cum le stie omul; inmultirea cu 1000
     spre unitatile nucleului (kHz, respectiv simboluri/s) se face intr-un singur loc, in
     transpondere_pachet(). Inainte, valorile erau scrise ca si cum ar fi fost deja in kHz si se mai
     inmulteau o data, deci plecau de 1000 de ori prea mari.
  3. pozitia orbitala e valoarea BRUTA pe care o asteapta eDVBFrontendParametersSatellite, 0..3599:
     0,8 grade vest = 3600 - 8 = 3592, nu "-8". (Confirmat pe date reale de receptor: namespace
     E080000 = orbpos 3592.) La est se scrie direct: 16,0 grade est = 160, 4,8 grade est = 48.

Codurile (sistem, polarizare, FEC, modulatie, rolloff, pilot) sunt cele din lib/dvb/frontendparms.h
(eDVBFrontendParametersSatellite), aceleasi pe care le foloseste si Screens/ScanerSatelit.py:
  sistem     0 = DVB-S, 1 = DVB-S2
  polarizare 0 = H, 1 = V, 2 = L, 3 = R
  FEC        0 = Auto, 1 = 1/2, 2 = 2/3, 3 = 3/4, 4 = 5/6, 5 = 7/8, 6 = 8/9, ...
  modulatie  1 = QPSK, 2 = 8PSK
  inversare  2 = Auto
Atentie: DVB-S2 nu primeste FEC Auto (lib/dvb/frontend.cpp, prepare_sat: "no valid fec for DVB-S2 set
.. abort"), de aceea pachetele DVB-S2 de mai jos au FEC si modulatie reale, nu Auto.

Modulul e numai date: nu importa nimic din enigma si nu porneste nimic.
"""

# Fiecare pachet: cheie interna, numele aratat, pozitia orbitala bruta si transponderul (sau
# transponderele) lui de plecare. Restul canalelor pachetului vin din tabelele retelei (NIT), de-aceea
# scanarea pachetului se porneste cu cautare in retea aprinsa.
PACHETE = [
    {
        'cheie': 'focus_sat',
        'nume': 'Focus Sat (0.8°W Thor)',
        'pozitie': 3592,                      # 0,8 grade VEST = 3600 - 8
        'transpondere': [
            # frecventa MHz, SR kSymb/s, polarizare, FEC, inversare, sistem, modulatie, rolloff, pilot
            {'frecventa': 11958, 'sr': 28000, 'pol': 1, 'fec': 5, 'inversare': 2,
             'sistem': 0, 'mod': 1, 'rolloff': 0, 'pilot': 0},
        ],
    },
    {
        'cheie': 'digi_sat',
        'nume': 'Digi TV Satelit (0.8°W Thor)',
        'pozitie': 3592,
        'transpondere': [
            {'frecventa': 12687, 'sr': 27500, 'pol': 0, 'fec': 3, 'inversare': 2,
             'sistem': 0, 'mod': 1, 'rolloff': 0, 'pilot': 0},
        ],
    },
    # cele doua intrari de mai jos aveau frecvente si pozitii care nu exista nici in satellites.xml,
    # nici in scanarile noastre (mostenite din ecranul vechi, fara sursa). Inlocuite cu ce am masurat noi pe
    # receptor. Focus Sat si Digi, de mai sus, au fost
    # verificate si erau corecte.
    {
        'cheie': 'dab_sat',
        'nume': 'Radiouri DAB+ prin satelit (39,0°E)',
        'pozitie': 390,                       # 39,0 grade est (Hellas Sat)
        'transpondere': [
            {'frecventa': 12242, 'sr': 30000, 'pol': 0, 'fec': 2, 'inversare': 2,
             'sistem': 1, 'mod': 2, 'rolloff': 0, 'pilot': 0},
        ],
    },
    {
        # ATENTIE: fluxul DVB-T2 prin satelit foloseste multistream (flux 0, PLS Gold 242133). Intrarea de aici nu
        # are fluxul si PLS-ul (is_id, pls_mode, pls_code), deci singura n-ar prinde nimic; felul „DVB-T2 prin
        # satelit” ia transponderul din data/operatori-satelit.json, cu fluxul si PLS-ul.
        'cheie': 'dvbt2_sat',
        'nume': 'Pachete DVB-T2 prin satelit (39,0°E)',
        'pozitie': 390,                       # 39,0 grade est (Hellas Sat)
        'transpondere': [
            {'frecventa': 11760, 'sr': 30000, 'pol': 0, 'fec': 2, 'inversare': 2,
             'sistem': 1, 'mod': 2, 'rolloff': 0, 'pilot': 0},
        ],
    },
]

CHEI = [p['cheie'] for p in PACHETE]


def lista_pachete():
    """[(cheie, nume)] pentru campul de alegere din ecran, in ordinea de mai sus."""
    return [(p['cheie'], p['nume']) for p in PACHETE]


def pachet(cheie):
    """Pachetul cu cheia data, sau None."""
    for p in PACHETE:
        if p['cheie'] == cheie:
            return p
    return None


def nume_pachet(cheie):
    p = pachet(cheie)
    return p['nume'] if p else str(cheie)


def pozitie_pachet(cheie):
    """Pozitia orbitala bruta (0..3599) a pachetului, sau None daca cheia nu exista."""
    p = pachet(cheie)
    return p['pozitie'] if p else None


def transpondere_pachet(cheie):
    """Transponderele pachetului in unitatile nucleului: frecventa in kHz, SR in simboluri/s.

    Singurul loc unde se face inmultirea cu 1000 (vezi punctul 2 din antet). Campurile si numele lor
    sunt exact cele ale lui eDVBFrontendParametersSatellite, ca sa poata fi date direct mai departe.
    Intoarce [] daca cheia nu exista.
    """
    p = pachet(cheie)
    if not p:
        return []
    lista = []
    for t in p['transpondere']:
        lista.append({
            'frequency': t['frecventa'] * 1000,      # MHz -> kHz
            'symbol_rate': t['sr'] * 1000,           # kSymb/s -> simboluri/s
            'polarisation': t['pol'],
            'fec': t['fec'],
            'inversion': t['inversare'],
            'orbital_position': p['pozitie'],
            'system': t['sistem'],
            'modulation': t['mod'],
            'rolloff': t['rolloff'],
            'pilot': t['pilot'],
        })
    return lista
