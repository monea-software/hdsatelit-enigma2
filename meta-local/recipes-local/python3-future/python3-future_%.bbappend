# Fisierele de proba ale bibliotecii (future/backports/test, cu chei .pem de test) nu trebuie pe receptor: nu le foloseste nimic
# la rulare, iar o cheie privata, chiar de proba, nu are ce cauta intr-o imagine (auditul din 04.11.2026).
PR:append = ".hds1"
do_install:append() {
	rm -rf ${D}${PYTHON_SITEPACKAGES_DIR}/future/backports/test
}
