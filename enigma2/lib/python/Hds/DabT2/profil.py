# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ce deosebeste HdsDab de HdsT2mi. Restul codului comun primeste un Profil si nu stie de care plugin tine.
Facut de hdsatelit.com."""
from .limba import N_

# DAB: felurile care vin prin portul 8001 pe un serviciu purtator (TS intreg, fara pierderi, ca T2-MI); TAP pierde
# ~35% pe HiSilicon. EDI ramane pe sectiuni MPE, cu tunerul tinut de plugin.
FELURI_ETI = ('ts2na', 'ts2na12', 'tsniv2ni')

# Textul „Despre" din ferestre, in imagine. Pluginul pentru alte imagini pune textul lui (plugin.py, inainte de
# prima fereastra); ecrane.py il citeste la deschidere.
DESPRE = N_('DAB+ si DVB-T2 din satelit, parte din imaginea HDSatelit. Facut de hdsatelit.com.')


class Profil(object):
    def __init__(self, **k):
        self.nume = k['nume']                  # HdsDab / HdsT2mi (numele directorului din Extensions)
        self.tip = k['tip']                    # dab / t2 (tipul feed-urilor din lista)
        self.titlu = k['titlu']
        self.eticheta = k['eticheta']          # in jurnal
        self.port = k['port']                  # portul releului pe 127.0.0.1
        self.prefix_url = k['prefix_url']      # /dab/ sau /t2/
        self.releu = k['releu']                # scriptul din motor/
        self.buchet = k['buchet']              # userbouquet.*.radio / .tv
        self.nume_buchet = k['nume_buchet']
        self.index_buchete = k['index_buchete']  # bouquets.radio / bouquets.tv
        self.tip_index = k['tip_index']        # 2 radio, 1 tv (in linia FROM BOUQUET)
        self.director = k['director']          # /etc/enigma2/hdsdab
        self.config = k['config']              # numele subsectiunii din config.plugins
        self.tmp = '/tmp'
        # DAB tine singur tunerul (canal brut + filtre pe demux). T2 NU: pachetele T2-MI vin doar prin portul 8001
        # al enigma2 (dovedit pe receptor), pe un serviciu purtator din lamedb; tunerul il ia streamserver-ul.
        self.tine_tuner = k.get('tine_tuner', True)
        # portul pe care releul raspunde la /stare si /servicii. T2 (0.1.3): fluxul il serveste binarul t2mi_decap pe
        # `port`, iar releul Python raspunde pe portul de control (port + 1). DAB: acelasi port.
        self.port_control = k.get('port_control', self.port)
        # porturi folosite de versiuni mai vechi in referintele din buchet; numai pentru recunoastere, nu se leaga
        self.porturi_vechi = tuple(k.get('porturi_vechi', ()))
        # DAB: sunetul cerut ca TS cu un program („<SID>.ts”, tipul 1, decodorul placii). Il pune imagine.py; pluginul
        # pentru alte imagini ramane pe LOAS / MP2 brut prin 4097 (buchete.forma_dab)
        self.sunet_ts = bool(k.get('sunet_ts', False))

    def porturi_ref(self):
        """Porturile dupa care o referinta din buchet e a acestui profil: cel curent, apoi cele vechi."""
        return (self.port,) + tuple(p for p in self.porturi_vechi if p != self.port)

    def fisier_feed(self):
        return '%s/%s-feed.json' % (self.tmp, self.nume.lower())

    def fisier_erori_releu(self):
        return '%s/%s-releu.err' % (self.tmp, self.nume.lower())

    def url_releu(self, cale):
        """/stare, /dab/.../lista, /t2/.../servicii: portul de control al releului."""
        return 'http://127.0.0.1:%d%s' % (self.port_control, cale)


# DAB pe 8898 din 0.1.9: 8888 e ocupat pe receptor de interfata web a altui program (bind -> EADDRINUSE, releul nu
# porneste). 8898 nu e folosit de nimic din imagine (netstat pe receptor). Referintele vechi pe 8888 raman
# recunoscute (porturi_vechi): refacerea buchetului le rescrie cu portul nou in loc sa le dubleze, la pornire toate
# buchetele utilizatorului se rescriu o data (buchete.rescrie_porturi_vechi), iar un zap pe o referinta veche ramasa
# in alta parte se reda pe portul nou (pornire.Controlor._extensie_zap).
DAB = Profil(nume='HdsDab', tip='dab', titlu=N_('DAB+ din satelit'), eticheta='dab', port=8898,
             prefix_url='/dab/', releu='releu_dab.py', buchet='userbouquet.hds_dab.radio',
             nume_buchet=N_('DAB+ din satelit'), index_buchete='bouquets.radio', tip_index=2,
             director='/etc/enigma2/hdsdab', config='hdsdab', porturi_vechi=(8888,))

T2 = Profil(nume='HdsT2mi', tip='t2', titlu=N_('DVB-T2 din satelit'), eticheta='t2', port=8889,
            prefix_url='/t2/', releu='releu_t2.py', buchet='userbouquet.hds_t2.tv',
            nume_buchet=N_('DVB-T2 din satelit'), index_buchete='bouquets.tv', tip_index=1,
            director='/etc/enigma2/hdst2mi', config='hdst2mi', tine_tuner=False, port_control=8890)
