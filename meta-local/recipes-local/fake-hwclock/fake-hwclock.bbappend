# HDSatelit: cat ora e provizorie NU se scrie in fake-hwclock, nici periodic, nici la iesire; se scrie numai ora sigura.
#
# Reteta de baza (meta-oe-alliance/meta-oe/recipes-core/fake-hwclock/fake-hwclock.bb, citita doar pentru intelegere)
# are INITSCRIPT_PARAMS = "start 01 S . stop 25 0 6 .", adica si /etc/rc0.d/K25fake-hwclock si /etc/rc6.d/K25fake-hwclock:
# la oprire si la repornire `fake-hwclock save` scria ora de acum oricare ar fi ea, deci si o ora provizorie (de la un
# singur transponder, poate gresita). Cum `fake-hwclock save` nu scrie o ora mai mica decat cea salvata, o ora gresita
# din viitor revenea apoi la fiecare pornire.
#
# Aici ramane numai pornirea (S01: ora salvata pusa la pornire). Ora o salveaza enigma2, numai cand e sigura (NTP, doua
# transpondere sau RTC): lib/python/Components/HdsCeas.py, la 30 de minute, la trecerea la ora sigura, dupa NTP si la
# iesirea enigma2. Scriptul /bin/fake-hwclock si /etc/init.d/fake-hwclock raman neschimbate (`fake-hwclock save` se
# poate chema si de mana).
#
# Numele e fake-hwclock.bbappend, nu fake-hwclock_%.bbappend: reteta nu are versiune in nume, iar bitbake
# (lib/bb/cooker.py, get_file_appends) potriveste "_%" numai cu "fake-hwclock_<versiune>.bb".

INITSCRIPT_PARAMS = "start 01 S ."
