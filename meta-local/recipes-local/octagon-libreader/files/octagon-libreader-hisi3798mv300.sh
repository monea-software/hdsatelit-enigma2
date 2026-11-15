#!/bin/sh
# HD Satelit: pasii scriptului producatorului (rootfs-ul marit, /boot montat, libreader 720P_50), cu o singura
# deosebire: libreader porneste in fundal si pornirea il asteapta cel mult 60 de secunde sa devina demon (atunci
# programul pornit iese). Pe o placa a carei verificare de autorizare nu trece, libreader ramane in bucla lui, iar
# rcS merge mai departe (reteaua, accesul, urmarirea pornirii si diagnosticul), in loc sa stea la S05.

echo extend rootfs to max size
resize2fs /dev/mmcblk0p16

echo "libreader start!!!"
mount /dev/mmcblk0p3 /boot/
/usr/bin/libreader 720P_50 &
hds_p=$!
hds_t=0
while kill -0 "$hds_p" 2>/dev/null && [ "$hds_t" -lt 60 ]; do
	sleep 1
	hds_t=$((hds_t + 1))
done
if kill -0 "$hds_p" 2>/dev/null; then
	echo "[hds-libreader] libreader did not become a daemon in ${hds_t} s (board check?): the start goes on"
	mkdir -p /home/root/logs 2>/dev/null
	echo "$(date '+%Y-%m-%d %H:%M:%S') S05: libreader nu a devenit demon in ${hds_t} s; pornirea a mers mai departe" \
		>> /home/root/logs/hds-libreader.log 2>/dev/null
fi
sleep 2
