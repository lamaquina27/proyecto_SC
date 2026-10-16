#!/usr/bin/env bash
# Arranca un nodo de ComplexNet en un Ubuntu en vivo cargado con "toram".
#
#   sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 1
#   sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 2 wlp2s0
#   sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh 3 --grupos rescate
#
# El numero de nodo da la IP (10.10.0.N) y el nombre (nodo-N). La tarjeta
# Wi-Fi se detecta sola; solo hace falta darla si el equipo tiene dos.
# Lo que va despues (--grupos ...) se le pasa a la aplicacion.
#
# Corrido desde la USB: copia todo a /opt/complexnet, desmonta la USB para
# que se pueda sacar y sigue desde la copia. Despues instala lo que falte
# desde paquetes/, revisa la tarjeta, monta la malla y abre la mensajeria.
#
# Para volver a abrir la aplicacion sin la USB:
#   sudo bash /opt/complexnet/arrancar_nodo.sh N
#
# La lista completa de pasos esta en PREPARAR_USB.md.

set -euo pipefail

DESTINO=/opt/complexnet
RED=10.10.0

fallar() { echo; echo "ERROR: $*" >&2; exit 1; }
paso() { echo; echo "== $* =="; }

[ "$(id -u)" -eq 0 ] || fallar "hay que correrlo con sudo:  sudo bash $0 $*"

NUM="${1:-}"
if ! [[ "$NUM" =~ ^[0-9]+$ ]] || [ "$NUM" -lt 1 ] || [ "$NUM" -gt 254 ]; then
  fallar "falta el numero de nodo (1 a 254). Ejemplo:  sudo bash $0 1"
fi
shift
WIFI=""
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
  WIFI="$1"
  shift
fi
EXTRA=("$@")

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------- 1. a la RAM
if [ "$ORIGEN" != "$DESTINO" ]; then
  if grep -qw "boot=casper" /proc/cmdline && ! grep -qw toram /proc/cmdline; then
    echo
    echo "OJO: este Linux NO arranco con 'toram'. Sigue funcionando, pero NO"
    echo "saques la USB de este computador o se cuelga. Para poder sacarla,"
    echo "reinicia y agrega 'toram' en el menu de arranque (PREPARAR_USB.md)."
    SE_PUEDE_SACAR=no
  else
    SE_PUEDE_SACAR=si
  fi

  paso "copiando el proyecto de la USB a la memoria ($DESTINO)"
  [ -d "$ORIGEN/complexnet-api" ] || fallar "no encuentro complexnet-api/ junto a este script ($ORIGEN)"
  rm -rf "$DESTINO"
  mkdir -p "$DESTINO"
  cp -r "$ORIGEN/complexnet-api" "$DESTINO/"
  cp "$ORIGEN"/*.sh "$DESTINO/"
  [ -d "$ORIGEN/paquetes" ] && cp -r "$ORIGEN/paquetes" "$DESTINO/"
  find "$DESTINO" -name '*.sh' -exec sed -i 's/\r$//' {} +
  sync
  echo "copiado."

  if [ "$SE_PUEDE_SACAR" = si ]; then
    cd /
    PUNTO="$(findmnt -n -o TARGET --target "$ORIGEN" 2>/dev/null || true)"
    if [ -n "$PUNTO" ] && [ "$PUNTO" != "/" ] && { umount "$PUNTO" 2>/dev/null || umount -l "$PUNTO" 2>/dev/null; }; then
      echo
      echo ">>> La USB quedo desmontada. YA LA PUEDES SACAR y llevarla al siguiente computador. <<<"
    else
      echo "No pude desmontar la USB. Expulsala desde la ventana de Archivos antes de sacarla."
    fi
  fi

  exec bash "$DESTINO/arrancar_nodo.sh" "$NUM" ${WIFI:+"$WIFI"} "${EXTRA[@]}"
fi

# ---------------------------------------------------------------- 2. programas
paso "revisando los programas necesarios"
instalar_si_falta() {
  local nombre="$1" deb
  if dpkg -s "$nombre" >/dev/null 2>&1; then
    return 0
  fi
  deb="$(compgen -G "$DESTINO/paquetes/${nombre}_*.deb" | sort | tail -n 1 || true)"
  if [ -z "$deb" ]; then
    echo "  falta $nombre y no esta en paquetes/"
    return 1
  fi
  if dpkg -i "$deb" >/dev/null 2>&1; then
    echo "  instalado $nombre (desde la USB)"
  else
    echo "  no se pudo instalar $nombre"
    return 1
  fi
}
for p in libnl-3-200 libnl-genl-3-200 iw batctl; do
  instalar_si_falta "$p" || true
done
instalar_si_falta python3-psutil || echo "  (psutil es opcional: sin el, cpu y memoria salen en 0.5)"

command -v iw >/dev/null || fallar "falta 'iw'. Pon iw_*.deb en paquetes/ (PREPARAR_USB.md, paso 3)."
command -v batctl >/dev/null || fallar "falta 'batctl'. Pon batctl_*.deb en paquetes/ (PREPARAR_USB.md, paso 3)."
command -v python3 >/dev/null || fallar "este Linux no trae python3."
echo "  iw, batctl y python3 listos."

# ---------------------------------------------------------------- 3. batman-adv
paso "cargando el modulo batman-adv"
if ! modprobe batman-adv 2>/dev/null; then
  extra="$(compgen -G "$DESTINO/paquetes/linux-modules-extra-$(uname -r)_*.deb" | sort | tail -n 1 || true)"
  if [ -n "$extra" ]; then
    echo "  instalando $(basename "$extra") ..."
    dpkg -i "$extra" >/dev/null && depmod -a
  fi
  modprobe batman-adv 2>/dev/null || fallar "este Linux no trae batman-adv para el kernel $(uname -r).
  Solucion: descarga linux-modules-extra-$(uname -r) y ponlo en paquetes/ (PREPARAR_USB.md, problemas)."
fi
echo "  batman-adv cargado."

# ---------------------------------------------------------------- 4. la tarjeta
paso "revisando la tarjeta Wi-Fi"
if [ -z "$WIFI" ]; then
  WIFI="$(iw dev 2>/dev/null | awk '$1 == "Interface" && $2 != "bat0" && !hay {print $2; hay = 1}' || true)"
  [ -n "$WIFI" ] || fallar "no encuentro ninguna tarjeta Wi-Fi ('iw dev' no muestra nada)."
fi
iw dev "$WIFI" info >/dev/null 2>&1 || fallar "'$WIFI' no es una tarjeta Wi-Fi. Mira las que hay con:  iw dev"
echo "  tarjeta: $WIFI"

PHY="phy$(iw dev "$WIFI" info | awk '/wiphy/ && !hay {print $2; hay = 1}')"
MODOS="$(iw phy "$PHY" info 2>/dev/null | grep -A 15 "Supported interface modes" || true)"
if ! grep -q '\* IBSS' <<< "$MODOS"; then
  fallar "la tarjeta $WIFI NO soporta el modo ad hoc (IBSS). Este computador no puede
  entrar a la malla; usa otro, o una tarjeta Wi-Fi USB que si lo soporte."
fi
echo "  soporta modo ad hoc (IBSS)."

# ---------------------------------------------------------------- 5. la malla
paso "montando la malla"
DIRECCIONES="$(ip -4 addr show bat0 2>/dev/null || true)"
if grep -q "inet $RED.$NUM/" <<< "$DIRECCIONES"; then
  echo "  la malla ya estaba montada en este equipo ($RED.$NUM)."
else
  rfkill unblock wifi 2>/dev/null || true
  if command -v nmcli >/dev/null; then
    nmcli device set "$WIFI" managed no 2>/dev/null || true
    sleep 1
  fi
  bash "$DESTINO/setup_adhoc.sh" "$NUM" "$WIFI"
fi

# ---------------------------------------------------------------- 6. la aplicacion
paso "abriendo la mensajeria como nodo-$NUM ($RED.$NUM)"
echo "  Escribe 'ayuda' para ver los comandos y 'salir' para cerrar."
echo "  Para volver a abrirla:  sudo bash $DESTINO/arrancar_nodo.sh $NUM"
echo "  El registro queda en:   $DESTINO/complexnet-api/logs/"
cd "$DESTINO/complexnet-api"
exec python3 applications/mensajeria.py --nombre "nodo-$NUM" "${EXTRA[@]}"
