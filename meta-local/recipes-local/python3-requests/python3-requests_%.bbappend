# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Imaginea mica (0.7.4, 10.11.2026): reteta meta-python cere la rulare si python3-chardet (12 MB necomprimat: chardet 6
# are modelele de limbi mari) si python3-charset-normalizer. requests 2.33 cauta intai chardet, iar fara el ia singur
# charset_normalizer (requests/compat.py), care e deja in imagine; deci detectarea codarii textelor merge la fel.
# Nimic din codul imaginii nu importa chardet (cautat in lib/python). requests il cere numai el (pkgdata gbmv200,
# runtime/python3-requests). Un plugin strain care cere chardet il primeste din feed, prin dependinta lui.
# Proba pe receptor fara chardet: python3 -c "import requests; print(requests.compat.chardet)" arata charset_normalizer.
RDEPENDS:${PN}:remove = "python3-chardet"
