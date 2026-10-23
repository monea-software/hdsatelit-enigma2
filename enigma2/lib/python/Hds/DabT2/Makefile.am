SUBDIRS = t2/bin

installdir = $(pkglibdir)/python/Hds/DabT2

# codul comun DAB+ / DVB-T2 (acelasi cu al pluginului pentru alte imagini) si imagine.py (pornirea din imagine)
install_PYTHON = \
	__init__.py aspect.py bataie.py buchete.py captura.py compat.py coordonator.py detector.py ecrane.py fir.py \
	fundal.py imagine.py intrare.py jurnal.py lamedb.py limba.py liste.py marcaj.py pornire.py proces.py profil.py \
	receptie.py releu_http.py scanare.py server8001.py sesiuni8001.py surse.py text_dvb.py tuner.py versiune.py

# releele (procese separate, pornite cu python3 <cale>) si listele de frecvente venite cu imaginea
nobase_install_PYTHON = \
	dab/motor/releu_dab.py dab/motor/dab_edi.py dab/motor/eti.py \
	t2/motor/releu_t2.py t2/motor/t2mi.py

nobase_dist_install_DATA = \
	dab/date/frecvente.json \
	t2/date/frecvente.json
