#!/usr/bin/env bash
# Prepara este equipo para la malla: Wi-Fi en modo ad hoc + batman-adv.
#
#   sudo ./setup_adhoc.sh 1          -> este equipo queda con 10.10.0.1
#   sudo ./setup_adhoc.sh 2 wlan1    -> usando otra interfaz
#
# Todos los equipos deben usar el mismo nombre de celda y el mismo canal.

set -euo pipefail

NUM="${1:?Falta el numero de nodo, por ejemplo: sudo ./setup_adhoc.sh 1}"
WIFI="${2:-wlan0}"
CELDA="complexnet"
FRECUENCIA=2412          # canal 1
RED="10.10.0"

if [ "$(id -u)" -ne 0 ]; then
  echo "Hay que correrlo con sudo."; exit 1
fi

echo "== cargando batman-adv =="
modprobe batman-adv

echo "== poniendo $WIFI en modo ad hoc =="
ip link set "$WIFI" down
iw dev "$WIFI" set type ibss
# MTU 1532: batman-adv le mete su cabecera a cada trama, y con 1500 en la
# interfaz de abajo bat0 quedaria por debajo de 1500 y fragmentaria.
ip link set "$WIFI" mtu 1532
ip link set "$WIFI" up
iw dev "$WIFI" ibss join "$CELDA" "$FRECUENCIA"

echo "== entregando $WIFI a batman-adv =="
batctl if add "$WIFI" 2>/dev/null || batctl meshif bat0 interface add "$WIFI"
ip link set up dev bat0
ip addr flush dev "$WIFI"
ip addr add "${RED}.${NUM}/24" dev bat0

echo
echo "Listo. bat0 = ${RED}.${NUM}"
ip -brief addr show bat0
echo
echo "Vecinos directos (puede tardar unos segundos en aparecer):"
batctl neighbors || true
echo
echo "Para ver todos los destinos alcanzables:  batctl originators"
echo "Para ver el camino hasta otro nodo:       batctl traceroute <MAC>"
