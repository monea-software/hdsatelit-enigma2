bin_SCRIPTS = enigma2.sh hds-rezerva.sh hds-rezerva-ecran.py hds-raport.sh hds-actualizare-intrerupta.py
lib_LTLIBRARIES = libopen.la

libopen_la_SOURCES = libopen.c
libopen_la_LIBADD = @LIBDL_LIBS@

# hds-blindscan: cautarea oarba pe satelit, proces separat pornit la cerere de Components/HdsCautareOarba.py (ecranul
# Screens/ScanerOarba.py si pagina web /oarba). Sta in pachetul interfetei, ca t2mi_decap, ca sa ajunga pe receptor cu
# orice actualizare, pe orice masina, fara pachet separat in feed; pe placile pe care nu stie calea tunerului refuza
# singur (SONDA/EROARE) si nu atinge nimic. Biblioteca platformei o incarca la rulare (dlopen), deci legam numai libdl
# si firele.
bin_PROGRAMS = hds-blindscan
hds_blindscan_SOURCES = hds-blindscan.c
hds_blindscan_CFLAGS = -std=gnu11 -Wall -Wextra -Werror=implicit-function-declaration -pthread \
	-DHDS_BLINDSCAN_VERSIUNE='"$(VERSION)"'
hds_blindscan_LDFLAGS = -pthread
hds_blindscan_LDADD = @LIBDL_LIBS@

# Aceste doua surse se instaleaza prin pachetul hdsatelit-nume-local.
# Pachetul detine deja initul; instalarea lui si aici ar dubla proprietarul.
EXTRA_DIST = enigma2.sh.in hds-rezerva.sh.in hds-raport.sh.in hds-nume-local hds-nume-local.py
