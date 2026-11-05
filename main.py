# main.py — JUEGOS DE MESA para Android (Kivy)
#
# Ajedrez (IA, 2 y 4 jugadores), Damas y 3 en raya, con partidas en red:
#  - ambos en la misma WiFi, o
#  - uno activa "Punto de acceso / Compartir internet" y el otro se conecta a esa WiFi.
# Las partidas creadas aparecen solas en la lista (descubrimiento automático).
#
# Archivos: main.py, gfx.py, juego_ajedrez.py, juego_damas.py, juego_tresenraya.py + imágenes.
import os
import sys
import json
import socket
import threading
import time
import collections
import traceback
from types import SimpleNamespace

from kivy.config import Config
Config.set("graphics", "resizable", "1")
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, PushMatrix, PopMatrix, Translate, Scale
from kivy.graphics.texture import Texture
from kivy.uix.widget import Widget
from kivy.utils import platform

from gfx import Gfx, Rect, Recursos
from juego_ajedrez import Ajedrez, Ajedrez4, GestorIA, NIVELES, NOM_ASIENTO, COL_ASIENTO
from juego_damas import Damas
from juego_tresenraya import TresEnRaya, MARGEN_TABLERO

ANDROID = platform == "android"

# ============================================================
# CONFIGURACIÓN
# ============================================================
W, H = 948, 648                    # lienzo virtual (se escala a la pantalla real)
TAM = 76
BX, BY = 20, 20
PX = BX + 8 * TAM + 20
PW = W - PX - 20

PUERTO = 50007
PUERTO_DESCUBRIR = 50008
MAGIA = b"DESCUBRIR_JUEGOS_LAN"

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA_DATOS = DIR_BASE            # en build() pasa a ser la carpeta privada de la app
ARCHIVO_CONFIG = os.path.join(CARPETA_DATOS, "config.json")

TITULOS = {"ajedrez": "Ajedrez", "damas": "Damas", "tresenraya": "3 en raya"}
ETQ_CLAVE = {"ajedrez": "Ajedrez · 2 jugadores", "ajedrez4": "Ajedrez · 4 jugadores",
             "damas": "Damas", "tresenraya": "3 en raya"}
CLAVES_LAN = {"ajedrez": ("ajedrez", "ajedrez4"), "damas": ("damas",),
              "tresenraya": ("tresenraya",)}

C_BG1 = (20, 24, 34)
C_BG2 = (34, 40, 58)
C_CARD = (38, 44, 60)
C_CARD2 = (30, 35, 48)
C_BORDE = (66, 74, 98)
C_TEXTO = (236, 239, 246)
C_SUAVE = (150, 160, 184)
C_ACENTO = (118, 190, 96)
C_AVISO = (255, 214, 102)
COLORES_TABLERO = [(240, 217, 181), (181, 136, 99)]

ESTILOS = {
    "primario": (70, 150, 82), "azul": (58, 110, 176), "dorado": (190, 142, 44),
    "rojo": (172, 62, 62), "gris": (68, 76, 96), "morado": (112, 82, 180),
}

# (tamaño, negrita)
FUENTES = {
    "titulo": (52, True), "h1": (34, True), "h2": (28, True), "h3": (21, True),
    "normal": (19, False), "normal_b": (19, True), "chica": (16, False), "coord": (14, True),
}

# ============================================================
# ESTADO GLOBAL
# ============================================================
# MENU, SUBMENU, LAN, ESPERANDO, LOBBY4, CONECTANDO, NIVEL, CARGANDO_IA, JUEGO, FIN
ESTADO = "MENU"
MENSAJE_ESTADO = ""
NOMBRE_LOCAL = "Jugador"
NOMBRE_RIVAL = ""
SALIR = False
IP_TEXTO = ""
CONFIRMAR = None
RECTS = {}
IMG_MENU = {}
FONDO_TEX = None
FALTAN = []
RES = None                  # gestor de imágenes
G = None                    # contexto de dibujo

JUEGO_SEL = "ajedrez"       # juego elegido en el menú
MODO = "local"              # local | ia | lan | local4 | lan4
JUEGOS = {}
juego = None                # juego de 2 lados activo
j4 = None                   # ajedrez de 4 jugadores
ia = None                   # gestor de IA
MI_LADO = 0
MI_ASIENTO = 0
REV_PROPIA = False
REV_RIVAL = False
CARGANDO_MSG = ""

# LAN
HOSTS_ENCONTRADOS = []      # [(ip, nombre, clave)]
HOST_SELECC = None
BUSCANDO = False
ULTIMA_BUSQ = 0.0
INVITACION_ENTRANTE = []
HOSTING = False
HOST_CLAVE = ""
srv_sock = None
conexion = None
CONEX_PEND = None
OCUPADO = False
IP_LOCAL = ""
ES_HOST4 = False
LOBBY = [None] * 4
CLIENTES4 = {}
COLA = collections.deque()
_MLOCK = None
ERRORES = 0


def nombre_local():
    return NOMBRE_LOCAL.strip() or "Jugador"


def ir(estado, msg=""):
    global ESTADO, MENSAJE_ESTADO
    ESTADO = estado
    MENSAJE_ESTADO = msg


def cargar_nombre():
    global NOMBRE_LOCAL
    try:
        with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
            nombre = str(json.load(f).get("nombre", "")).strip()
        if nombre:
            NOMBRE_LOCAL = nombre[:16]
    except Exception:
        pass


def guardar_nombre():
    try:
        os.makedirs(CARPETA_DATOS, exist_ok=True)
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"nombre": NOMBRE_LOCAL.strip()}, f, ensure_ascii=False)
    except Exception:
        pass


# ============================================================
# ANDROID: pantalla encendida y permiso para recibir broadcast WiFi
# ============================================================
def preparar_android():
    """Mantiene la pantalla encendida y activa el 'multicast lock' (sin él, muchos
    celulares descartan los paquetes de descubrimiento). Todo es opcional: si falla, sigue."""
    global _MLOCK
    if not ANDROID:
        return
    try:
        from jnius import autoclass, cast
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        try:
            from android.runnable import run_on_ui_thread

            @run_on_ui_thread
            def _pantalla():
                act.getWindow().addFlags(128)          # FLAG_KEEP_SCREEN_ON
            _pantalla()
        except Exception as e:
            print("AVISO pantalla encendida:", e)
        wifi = cast("android.net.wifi.WifiManager", act.getSystemService("wifi"))
        _MLOCK = wifi.createMulticastLock("juegos_de_mesa")
        _MLOCK.setReferenceCounted(False)
        _MLOCK.acquire()
    except Exception as e:
        print("AVISO multicast lock:", e)


def liberar_android():
    global _MLOCK
    try:
        if _MLOCK is not None and _MLOCK.isHeld():
            _MLOCK.release()
    except Exception:
        pass
    _MLOCK = None


# ============================================================
# RED
# ============================================================
class Conexion:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = b""
        self.activa = True
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass

    def enviar(self, msg):
        if not self.activa:
            return
        try:
            self.sock.sendall(json.dumps(msg).encode() + b"\n")
        except Exception:
            self.activa = False

    def recibir_uno(self):
        try:
            while b"\n" not in self.buffer:
                datos = self.sock.recv(4096)
                if not datos:
                    self.activa = False
                    return None
                self.buffer += datos
            linea, self.buffer = self.buffer.split(b"\n", 1)
            return json.loads(linea.decode())
        except Exception:
            self.activa = False
            return None

    def cerrar(self):
        self.activa = False
        try:
            self.sock.close()
        except Exception:
            pass


_CELULAR = ("rmnet", "ccmni", "tun", "ppp", "dummy", "v4-", "clat", "ipsec", "sit")


def interfaces_red():
    """[(nombre, ip, broadcast|None)] de las redes locales activas.
    Incluye la WiFi normal Y la del 'punto de acceso' (hotspot) del propio celular."""
    res = []
    if ANDROID:
        try:
            from jnius import autoclass
            NI = autoclass("java.net.NetworkInterface")
            lista = autoclass("java.util.Collections").list(NI.getNetworkInterfaces())
            for i in range(lista.size()):
                ni = lista.get(i)
                try:
                    if (not ni.isUp()) or ni.isLoopback():
                        continue
                    nombre = str(ni.getName())
                    if nombre.lower().startswith(_CELULAR):
                        continue
                    ias = ni.getInterfaceAddresses()
                    for k in range(ias.size()):
                        ia_ = ias.get(k)
                        ip = str(ia_.getAddress().getHostAddress())
                        if ":" in ip or ip.startswith("127.") or ip.startswith("169.254."):
                            continue
                        b = ia_.getBroadcast()
                        res.append((nombre, ip, str(b.getHostAddress()) if b else None))
                except Exception:
                    continue
        except Exception as e:
            print("AVISO interfaces:", e)
    if not res:                                   # PC / respaldo
        ips = []
        try:
            ips += socket.gethostbyname_ex(socket.gethostname())[2]
        except Exception:
            pass
        for destino in ("10.255.255.255", "192.168.255.255", "8.8.8.8"):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((destino, 80))
                ips.append(s.getsockname()[0])
                s.close()
            except Exception:
                pass
        for ip in dict.fromkeys(ips):
            if ip and not ip.startswith("127.") and not ip.startswith("0."):
                res.append(("red", ip, None))
    pref = ("wlan", "ap", "swlan", "softap", "eth", "wigig", "p2p")
    res.sort(key=lambda t: 0 if t[0].lower().startswith(pref) else 1)
    return res


def ips_locales():
    vistos = []
    for _, ip, _ in interfaces_red():
        if ip not in vistos:
            vistos.append(ip)
    return vistos


def hilo_lector(c):
    """Lee mensajes de una conexión y los deja en COLA (se procesan en el hilo principal)."""
    while c.activa:
        msg = c.recibir_uno()
        if msg is None:
            break
        msg["_c"] = c
        COLA.append(msg)
    COLA.append({"tipo": "_eof", "_c": c})


# ---------- Servidor (host) ----------
def iniciar_host(clave):
    global srv_sock, HOSTING, HOST_CLAVE
    detener_host()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PUERTO))
        s.listen(8)
        s.settimeout(0.5)
    except OSError as e:
        return str(e)
    srv_sock = s
    HOST_CLAVE = clave
    HOSTING = True
    threading.Thread(target=hilo_servidor, args=(s,), daemon=True).start()
    return None


def detener_host():
    global srv_sock, HOSTING
    HOSTING = False
    if srv_sock is not None:
        try:
            srv_sock.close()
        except Exception:
            pass
        srv_sock = None
    for c, _ in list(INVITACION_ENTRANTE):
        c.cerrar()
    INVITACION_ENTRANTE.clear()


def hilo_servidor(s):
    while HOSTING and srv_sock is s:
        try:
            sock, _ = s.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=recibir_hola, args=(sock,), daemon=True).start()


def recibir_hola(sock):
    c = Conexion(sock)
    sock.settimeout(5)
    msg = c.recibir_uno()
    try:
        sock.settimeout(None)
    except Exception:
        pass
    if not msg or msg.get("tipo") != "hola" or not HOSTING:
        c.cerrar()
        return
    familia = HOST_CLAVE.rstrip("4")
    if msg.get("juego") != familia:
        c.enviar({"tipo": "rechazo", "motivo": f"Esa partida es de {TITULOS.get(familia, '?')}"})
        c.cerrar()
        return
    if OCUPADO:
        c.enviar({"tipo": "ocupado"})
        c.cerrar()
        return
    nombre = str(msg.get("nombre", "Rival"))[:16]
    if HOST_CLAVE == "ajedrez4":
        COLA.append({"tipo": "_nuevo4", "_c": c, "nombre": nombre})
    else:
        INVITACION_ENTRANTE.append((c, nombre))


# ---------- Cliente ----------
def unirse(ip):
    ip = ip.strip()
    if not ip:
        ir_lan("Escribe o selecciona una IP.")
        return
    ir("CONECTANDO", f"Conectando con {ip}...")
    threading.Thread(target=hilo_cliente, args=(ip, nombre_local(), JUEGO_SEL),
                     daemon=True).start()


def hilo_cliente(ip_host, nombre, familia):
    global CONEX_PEND
    c = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(6)
        sock.connect((ip_host, PUERTO))
        sock.settimeout(None)
        c = Conexion(sock)
        CONEX_PEND = c
        c.enviar({"tipo": "hola", "nombre": nombre, "juego": familia})
        msg = c.recibir_uno()
        if msg is None:
            COLA.append({"tipo": "_error", "_c": c, "txt": "El host no respondió."})
            c.cerrar()
            return
        msg["_c"] = c
        COLA.append(msg)
        if msg.get("tipo") in ("aceptado", "lobby"):
            hilo_lector(c)
        else:
            c.cerrar()
    except Exception as e:
        if c:
            c.cerrar()
        COLA.append({"tipo": "_error", "_c": c, "txt": f"No se pudo conectar: {e}"})


# ---------- Descubrimiento automático ----------
def lobby_lleno():
    return HOST_CLAVE == "ajedrez4" and sum(1 for n in LOBBY if n) >= 4


def hilo_respondedor_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", PUERTO_DESCUBRIR))
    except Exception as e:
        print("AVISO: no se pudo abrir el puerto de descubrimiento:", e)
        return
    while True:
        try:
            datos, addr = s.recvfrom(1024)
        except ConnectionResetError:
            continue
        except OSError:
            break
        if datos == MAGIA and HOSTING and not OCUPADO and not lobby_lleno():
            try:
                resp = json.dumps({"n": nombre_local(), "c": HOST_CLAVE}).encode("utf-8")
                s.sendto(resp, addr)
            except Exception:
                pass


def buscar_en_lan(timeout=1.6):
    """Busca partidas de dos maneras a la vez, para que funcione en cualquier router
    o punto de acceso: (1) broadcast y (2) envío directo a toda la subred /24."""
    ifs = interfaces_red()
    propias = {ip for _, ip, _ in ifs}
    difusion = {"255.255.255.255"}
    directo = set()
    for _, ip, bc in ifs[:3]:
        if bc:
            difusion.add(bc)
        p = ip.split(".")
        if len(p) == 4:
            difusion.add(".".join(p[:3] + ["255"]))
            base = ".".join(p[:3])
            for i in range(1, 255):
                d = f"{base}.{i}"
                if d != ip:
                    directo.add(d)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception:
        pass
    s.settimeout(0.3)
    for d in list(difusion) + sorted(directo):
        try:
            s.sendto(MAGIA, (d, PUERTO_DESCUBRIR))
        except Exception:
            pass
    encontrados = {}
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            datos, addr = s.recvfrom(1024)
            if addr[0] in propias:
                continue
            info = json.loads(datos.decode("utf-8", errors="ignore"))
            encontrados[addr[0]] = (str(info.get("n", "Jugador")), str(info.get("c", "")))
        except socket.timeout:
            continue
        except (ConnectionResetError, ValueError):
            continue
        except Exception:
            break
    s.close()
    return sorted((ip, n, c) for ip, (n, c) in encontrados.items())


def lanzar_busqueda():
    global BUSCANDO
    if BUSCANDO:
        return
    BUSCANDO = True
    threading.Thread(target=hilo_busqueda, daemon=True).start()


def hilo_busqueda():
    global BUSCANDO, HOSTS_ENCONTRADOS, HOST_SELECC, ULTIMA_BUSQ
    try:
        res = buscar_en_lan(1.6)
        HOSTS_ENCONTRADOS = res
        if HOST_SELECC not in [ip for ip, _, _ in res]:
            HOST_SELECC = None
    except Exception as e:
        print("AVISO búsqueda:", e)
    finally:
        ULTIMA_BUSQ = time.time()
        BUSCANDO = False


def ir_lan(msg=""):
    global HOSTS_ENCONTRADOS, HOST_SELECC, ULTIMA_BUSQ
    HOSTS_ENCONTRADOS = []
    HOST_SELECC = None
    ULTIMA_BUSQ = 0.0
    ir("LAN", msg)


def cerrar_conexiones():
    """Cierra todo lo relacionado con la red (avisando al otro lado)."""
    global conexion, CONEX_PEND, OCUPADO, ES_HOST4
    for cc in list(CLIENTES4.values()):
        cc.enviar({"tipo": "cerrar"})
        cc.cerrar()
    CLIENTES4.clear()
    if conexion:
        conexion.enviar({"tipo": "rendicion" if (ESTADO == "JUEGO" and MODO == "lan")
                         else "desconexion"})
        conexion.cerrar()
        conexion = None
    if CONEX_PEND:
        CONEX_PEND.cerrar()
        CONEX_PEND = None
    OCUPADO = False
    ES_HOST4 = False
    detener_host()


def crear_partida(clave):
    global IP_LOCAL, ES_HOST4, LOBBY, MI_ASIENTO
    err = iniciar_host(clave)
    if err:
        ir_lan(f"No se pudo crear la partida: {err}")
        return
    ips = ips_locales()
    IP_LOCAL = "  /  ".join(ips[:2]) if ips else "sin red"
    if clave == "ajedrez4":
        ES_HOST4 = True
        MI_ASIENTO = 0
        LOBBY = [nombre_local(), None, None, None]
        CLIENTES4.clear()
        ir("LOBBY4")
    else:
        ir("ESPERANDO")


def aceptar_invitacion(idx):
    global conexion, OCUPADO
    if idx >= len(INVITACION_ENTRANTE):
        return
    c, nombre = INVITACION_ENTRANTE.pop(idx)
    for otra, _ in list(INVITACION_ENTRANTE):
        otra.enviar({"tipo": "rechazo", "motivo": "Host ocupado"})
        otra.cerrar()
    INVITACION_ENTRANTE.clear()
    if not c.activa:
        ir("ESPERANDO", "Ese jugador ya se desconectó.")
        return
    clave = HOST_CLAVE
    conexion = c
    OCUPADO = True
    detener_host()
    c.enviar({"tipo": "aceptado", "lado": 1, "clave": clave, "nombre": nombre_local()})
    threading.Thread(target=hilo_lector, args=(c,), daemon=True).start()
    iniciar_lan2(clave, 0, nombre)


def rechazar_invitacion(idx):
    if idx >= len(INVITACION_ENTRANTE):
        return
    c, _ = INVITACION_ENTRANTE.pop(idx)
    c.enviar({"tipo": "rechazo", "motivo": "El host rechazó la partida"})
    c.cerrar()


# ============================================================
# FLUJO DE PARTIDAS
# ============================================================
def preparar(clave, modo, lado, rival):
    global juego, MODO, MI_LADO, NOMBRE_RIVAL, REV_PROPIA, REV_RIVAL, CONFIRMAR
    juego = JUEGOS[clave]
    MODO = modo
    MI_LADO = lado
    NOMBRE_RIVAL = rival
    juego.nueva(lado, orientar=(modo == "lan"))
    REV_PROPIA = REV_RIVAL = False
    CONFIRMAR = None
    ir("JUEGO")


def empezar_local():
    preparar(JUEGO_SEL, "local", 0, "Jugador 2")


def empezar_ia():
    preparar("ajedrez", "ia", 0, f"IA · {ia.titulo}")


def iniciar_lan2(clave, lado, rival):
    preparar(clave if clave in JUEGOS else JUEGO_SEL, "lan", lado, rival)


def empezar_local4():
    global MODO, CONFIRMAR
    j4.nueva([0, 1, 2, 3], 0, True)
    MODO = "local4"
    CONFIRMAR = None
    ir("JUEGO")


def iniciar4_host():
    global MODO, MI_ASIENTO, CONFIRMAR
    ocup = [s for s in range(4) if LOBBY[s]]
    if len(ocup) < 2:
        return
    detener_host()
    for s, cc in CLIENTES4.items():
        cc.enviar({"tipo": "inicio4", "asiento": s, "nombres": LOBBY})
    MI_ASIENTO = 0
    j4.nueva(ocup, 0, False)
    MODO = "lan4"
    CONFIRMAR = None
    ir("JUEGO")


def nueva4_host():
    """Nueva partida en LAN de 4: cada jugador pasa al siguiente color."""
    global MI_ASIENTO, LOBBY, MODO
    ocup = [s for s in range(4) if s == MI_ASIENTO or s in CLIENTES4]
    if len(ocup) < 2:
        ir("FIN", "No hay suficientes jugadores conectados.")
        return
    nombres = [None] * 4
    nuevos = {}
    nuevo_mio = MI_ASIENTO
    for i, s in enumerate(ocup):
        dest = ocup[(i + 1) % len(ocup)]
        nombres[dest] = LOBBY[s] or NOM_ASIENTO[s]
        if s in CLIENTES4:
            nuevos[dest] = CLIENTES4[s]
        if s == MI_ASIENTO:
            nuevo_mio = dest
    LOBBY = nombres
    CLIENTES4.clear()
    CLIENTES4.update(nuevos)
    MI_ASIENTO = nuevo_mio
    for s, cc in CLIENTES4.items():
        cc.enviar({"tipo": "inicio4", "asiento": s, "nombres": LOBBY})
    j4.nueva([s for s in range(4) if LOBBY[s]], MI_ASIENTO, False)
    MODO = "lan4"
    ir("JUEGO")


def difundir_lobby():
    for s, cc in list(CLIENTES4.items()):
        cc.enviar({"tipo": "lobby", "asiento": s, "nombres": LOBBY})


def difundir4(msg, excepto=None):
    for cc in list(CLIENTES4.values()):
        if cc is not excepto:
            cc.enviar(msg)


def nombre_asiento(s):
    if MODO == "lan4" and LOBBY[s]:
        return LOBBY[s]
    return NOM_ASIENTO[s]


def mensaje_fin(r):
    tipo, quien, motivo = r
    if MODO in ("lan4", "local4"):
        if tipo == "tablas":
            return f"Tablas: {motivo}."
        if MODO == "lan4":
            return "¡Ganaste!" if quien == MI_ASIENTO else f"Ganó {nombre_asiento(quien)}."
        return f"¡Ganó {NOM_ASIENTO[quien]}!"
    if tipo == "tablas":
        return motivo + "."
    if MODO == "local":
        return f"Gana {juego.lados[quien]} ({motivo})"
    return f"¡Ganaste! ({motivo})" if quien == MI_LADO else f"Perdiste esta vez ({motivo})"


def comprobar_fin():
    if ESTADO != "JUEGO":
        return False
    r = (j4 if MODO in ("lan4", "local4") else juego).resultado()
    if not r:
        return False
    ir("FIN", mensaje_fin(r))
    return True


def pedir_revancha():
    global REV_PROPIA
    if REV_PROPIA or not conexion:
        return
    REV_PROPIA = True
    conexion.enviar({"tipo": "revancha"})
    if REV_RIVAL:
        aplicar_revancha()


def aplicar_revancha():
    preparar(juego.clave, "lan", 1 - MI_LADO, NOMBRE_RIVAL)       # se intercambian los colores


def reiniciar_partida():
    if MODO == "ia":
        ia.cancelar()
        juego.nueva(0)
        ir("JUEGO")
    elif MODO == "local":
        juego.nueva(0)
        ir("JUEGO")
    elif MODO == "local4":
        empezar_local4()


def rehacer_jugada():
    if MODO != "ia" or ia.pensando or not juego.board.move_stack:
        return
    ia.cancelar()
    juego.deshacer()
    ir("JUEGO")


def volver_menu():
    global CONFIRMAR
    cerrar_conexiones()
    if ia:
        ia.cerrar()
    CONFIRMAR = None
    ir("MENU")


def volver_elo():
    global CONFIRMAR
    ia.cerrar()
    CONFIRMAR = None
    ir("NIVEL")


def puede_mover():
    if ESTADO != "JUEGO":
        return False
    if MODO == "local":
        return True
    if MODO == "ia":
        return juego.turno == 0 and not ia.pensando
    return juego.turno == MI_LADO


def clic_tablero(pos):
    if ESTADO != "JUEGO":
        return
    if MODO in ("lan4", "local4"):
        if MODO == "lan4" and j4.turno_asiento != MI_ASIENTO:
            return
        d = j4.clic(pos)
        if d is not None:
            if MODO == "lan4":
                if ES_HOST4:
                    difundir4({"tipo": "mov4", "d": d})
                elif conexion:
                    conexion.enviar({"tipo": "mov4", "d": d})
            comprobar_fin()
        return
    if not puede_mover():
        return
    d = juego.clic(pos)
    if d is None:
        return
    if MODO == "lan" and conexion:
        conexion.enviar({"tipo": "mov", "d": d})
    if not comprobar_fin() and MODO == "ia":
        ia.pensar(juego.board)


# ============================================================
# MENSAJES DE RED (se procesan en el hilo principal)
# ============================================================
def iniciar_modo4_cliente():
    global MODO, CONFIRMAR
    MODO = "lan4"
    CONFIRMAR = None
    ir("JUEGO")


def procesar_cola():
    global conexion, CONEX_PEND, OCUPADO, NOMBRE_RIVAL, MI_ASIENTO, LOBBY, ES_HOST4, REV_RIVAL
    while COLA:
        msg = COLA.popleft()
        t = msg.get("tipo")
        c = msg.get("_c")

        if t == "_error":
            if ESTADO == "CONECTANDO":
                CONEX_PEND = None
                ir_lan(msg.get("txt", "Error de conexión."))
            continue

        if t == "_nuevo4":
            libres = [s for s in (1, 2, 3) if LOBBY[s] is None]
            if ESTADO != "LOBBY4" or not ES_HOST4 or not libres:
                c.enviar({"tipo": "ocupado"})
                c.cerrar()
                continue
            s = libres[0]
            LOBBY[s] = msg.get("nombre", "Jugador")
            CLIENTES4[s] = c
            threading.Thread(target=hilo_lector, args=(c,), daemon=True).start()
            difundir_lobby()
            continue

        # --- respuesta del host a mi intento de conexión
        if c is not None and c is CONEX_PEND:
            if t == "ocupado":
                c.cerrar()
                CONEX_PEND = None
                ir_lan("El host ya está jugando.")
            elif t == "rechazo":
                c.cerrar()
                CONEX_PEND = None
                ir_lan(f"Rechazado: {msg.get('motivo', '')}")
            elif t == "aceptado":
                conexion, CONEX_PEND, OCUPADO = c, None, True
                NOMBRE_RIVAL = str(msg.get("nombre", "Host"))[:16]
                iniciar_lan2(msg.get("clave", JUEGO_SEL), int(msg.get("lado", 1)), NOMBRE_RIVAL)
            elif t == "lobby":
                conexion, CONEX_PEND, ES_HOST4 = c, None, False
                MI_ASIENTO = int(msg.get("asiento", 1))
                LOBBY = list(msg.get("nombres", [None] * 4))
                ir("LOBBY4")
            elif t == "_eof":
                CONEX_PEND = None
                if ESTADO == "CONECTANDO":
                    ir_lan("El host no respondió.")
            continue

        # --- mi conexión de partida (2 jugadores, o cliente de 4 jugadores)
        if c is not None and c is conexion:
            if t == "mov" and ESTADO == "JUEGO" and MODO == "lan":
                if juego.turno != MI_LADO:
                    juego.aplicar(msg.get("d"))
                    comprobar_fin()
            elif t == "revancha":
                REV_RIVAL = True
                if REV_PROPIA:
                    aplicar_revancha()
            elif t in ("rendicion", "desconexion"):
                if ESTADO == "JUEGO":
                    if t == "rendicion":
                        ir("FIN", f"{NOMBRE_RIVAL} abandonó la partida. ¡Ganaste!")
                    else:
                        ir("FIN", "El rival se desconectó.")
            elif t == "lobby":
                MI_ASIENTO = int(msg.get("asiento", MI_ASIENTO))
                LOBBY = list(msg.get("nombres", LOBBY))
            elif t == "inicio4":
                MI_ASIENTO = int(msg.get("asiento", 1))
                LOBBY = list(msg.get("nombres", LOBBY))
                OCUPADO = True
                j4.nueva([s for s in range(4) if LOBBY[s]], MI_ASIENTO, False)
                iniciar_modo4_cliente()
            elif t == "mov4" and MODO == "lan4" and ESTADO == "JUEGO":
                j4.aplicar(msg.get("d"))
                comprobar_fin()
            elif t == "elim4" and MODO == "lan4" and ESTADO == "JUEGO":
                j4.eliminar(int(msg.get("seat", -1)))
                comprobar_fin()
            elif t in ("cerrar", "_eof"):
                if ESTADO == "LOBBY4":
                    cerrar_conexiones()
                    ir_lan("El host cerró la sala.")
                elif ESTADO == "JUEGO":
                    ir("FIN", "El host cerró la partida." if MODO == "lan4"
                       else "Conexión perdida con el rival.")
            continue

        # --- host de 4 jugadores: mensajes de los clientes
        if ES_HOST4 and c is not None and c in CLIENTES4.values():
            seat = next(s for s, cc in CLIENTES4.items() if cc is c)
            if t == "mov4":
                if ESTADO == "JUEGO" and j4.validar(seat, msg.get("d", [])):
                    j4.aplicar(msg["d"])
                    difundir4({"tipo": "mov4", "d": msg["d"]}, excepto=c)
                    comprobar_fin()
            elif t == "_eof":
                del CLIENTES4[seat]
                c.cerrar()
                if ESTADO == "LOBBY4":
                    LOBBY[seat] = None
                    difundir_lobby()
                elif ESTADO == "JUEGO":
                    j4.eliminar(seat)
                    difundir4({"tipo": "elim4", "seat": seat})
                    comprobar_fin()


# ============================================================
# UTILIDADES DE DIBUJO
# ============================================================
def aclarar(c, d):
    return tuple(min(255, v + d) for v in c)


def texto(p, s, x, y, fuente, color=C_TEXTO, centro=False, derecha=False, max_w=None):
    return p.texto(s, x, y, fuente, color, centro, derecha, max_w)


def tarjeta(p, rect, color=C_CARD, borde=C_BORDE, radio=14):
    p.rect(color, rect, radio)
    p.rect(borde, rect, radio, borde=1)


def boton(p, rect, txt, estilo="gris", activo=True, nombre=None, fuente=None):
    fuente = fuente or FUENTES["normal_b"]
    base = ESTILOS[estilo] if activo else (52, 57, 70)
    p.rect((12, 14, 20), rect.move(0, 3), 11)
    p.rect(base, rect, 11)
    p.rect(aclarar(base, 30) if activo else (70, 75, 90), rect, 11, borde=1)
    tc = C_TEXTO if activo else (120, 128, 146)
    s = p.recortar(txt, fuente, rect.w - 16)
    _, h = p.medir(s, fuente)
    p.texto(s, rect.centerx, rect.centery - h / 2.0, fuente, tc, centro=True)
    if nombre and activo:
        RECTS[nombre] = rect
    return rect


def campo(p, rect, valor, nombre, placeholder=""):
    """Caja de texto: al tocarla se abre el teclado del celular."""
    p.rect((24, 28, 40), rect, 10)
    p.rect(C_BORDE, rect, 10, borde=2)
    f = FUENTES["normal"]
    _, h = p.medir("Ag", f)
    if valor:
        texto(p, valor, rect.x + 12, rect.centery - h / 2.0, f, max_w=rect.w - 24)
    else:
        texto(p, placeholder, rect.x + 12, rect.centery - h / 2.0, f, C_SUAVE)
    RECTS[nombre] = rect


def encabezado(p, titulo, subtitulo=None, volver=True):
    if volver:
        boton(p, Rect(20, 18, 130, 40), "<  Volver", "gris", nombre="volver",
              fuente=FUENTES["normal"])
    texto(p, titulo, W // 2, 14, FUENTES["h1"], centro=True, max_w=W - 340)
    if subtitulo:
        texto(p, subtitulo, W // 2, 62, FUENTES["normal"], C_SUAVE, centro=True, max_w=W - 40)


# ============================================================
# PANTALLAS
# ============================================================
def dib_mini3r(p, x, y, tam):
    """Mini tablero de 3 en raya (tu tablero + tus X y O) para el menú."""
    tab = RES.cargar_fit("tablero_3_en_raya.png", tam, tam)
    if tab:
        ax, ay, aw, ah = x + (tam - tab.w) // 2, y + (tam - tab.h) // 2, tab.w, tab.h
        p.img(tab, ax, ay)
    else:
        ax, ay, aw, ah = x + 6, y + 6, tam - 12, tam - 12
        p.rect((240, 240, 240), (ax, ay, aw, ah), 8)
        for i in (1, 2):
            p.linea((60, 60, 60), (ax + i * aw // 3, ay), (ax + i * aw // 3, ay + ah), 3)
            p.linea((60, 60, 60), (ax, ay + i * ah // 3), (ax + aw, ay + i * ah // 3), 3)
    ml, mt, mr, mb = MARGEN_TABLERO
    gx, gy = ax + int(aw * ml), ay + int(ah * mt)
    gw, gh = int(aw * (1 - ml - mr)), int(ah * (1 - mt - mb))
    cw, ch = gw / 3, gh / 3
    lado = int(min(cw, ch) * 0.70)
    equis = RES.cargar_fit("equis_3_en_raya.png", lado, lado)
    circ = RES.cargar_fit("circulo_3_en_raya.png", lado, lado)
    for idx, img in ((0, equis), (4, equis), (8, equis), (2, circ), (3, circ)):
        if img:
            f, c = divmod(idx, 3)
            cx = int(round(gx + (c + 0.5) * cw))
            cy = int(round(gy + (f + 0.5) * ch))
            p.img(img, cx - img.w // 2, cy - img.h // 2)


def tarjeta_juego(p, rect, titulo, sub, img, nombre):
    p.rect((12, 14, 20), rect.move(0, 4), 16)
    p.rect(C_CARD, rect, 16)
    p.rect(C_BORDE, rect, 16, borde=2)
    if callable(img):
        img(p, rect.centerx - 56, rect.y + 24)
    elif img:
        p.img(img, rect.centerx - img.get_width() // 2, rect.y + 24)
    texto(p, titulo, rect.centerx, rect.y + 142, FUENTES["h2"], centro=True)
    texto(p, sub, rect.centerx, rect.y + 184, FUENTES["chica"], C_SUAVE, centro=True,
          max_w=rect.w - 20)
    RECTS[nombre] = rect


def pantalla_menu(p):
    texto(p, "JUEGOS DE MESA", W // 2, 26, FUENTES["titulo"], centro=True)
    texto(p, "Elige un juego", W // 2, 92, FUENTES["normal"], C_SUAVE, centro=True)

    cx = W // 2
    texto(p, "Tu nombre (toca para cambiarlo)", cx - 190, 130, FUENTES["chica"], C_SUAVE)
    campo(p, Rect(cx - 190, 152, 380, 42), NOMBRE_LOCAL, "campo_nombre", "Escribe tu nombre")

    cw, ch, gap = 250, 226, 24
    x0 = (W - (3 * cw + 2 * gap)) // 2
    datos = [("m_ajedrez", "Ajedrez", "IA · 2 · 4 jugadores · Red", "ajedrez"),
             ("m_damas", "Damas", "2 jugadores · Red", "damas"),
             ("m_3r", "3 en raya", "2 jugadores · Red", "tresenraya")]
    for i, (nom, tit, sub, k) in enumerate(datos):
        tarjeta_juego(p, Rect(x0 + i * (cw + gap), 226, cw, ch), tit, sub, IMG_MENU.get(k), nom)

    boton(p, Rect(cx - 130, 484, 260, 50), "Salir", "rojo", nombre="m_salir")
    if FALTAN:
        texto(p, f"Faltan {len(FALTAN)} imágenes (ej.: {FALTAN[0]}).",
              cx, 556, FUENTES["chica"], (255, 140, 120), centro=True, max_w=W - 40)
        texto(p, "Súbelas a GitHub junto a main.py y vuelve a generar el APK.",
              cx, 578, FUENTES["chica"], C_SUAVE, centro=True)
    elif MENSAJE_ESTADO:
        texto(p, MENSAJE_ESTADO, cx, 556, FUENTES["normal"], C_AVISO, centro=True, max_w=W - 40)


def pantalla_submenu(p):
    encabezado(p, TITULOS[JUEGO_SEL], "¿Cómo quieres jugar?")
    cx = W // 2
    if JUEGO_SEL == "ajedrez":
        ops = [("s_ia", "Jugar contra la IA", "morado"),
               ("s_local", "2 jugadores en este celular", "primario"),
               ("s_local4", "4 jugadores en este celular", "dorado"),
               ("s_lan", "Partida en red (2 o 4 jugadores)", "azul")]
    else:
        ops = [("s_local", "2 jugadores en este celular", "primario"),
               ("s_lan", "Partida en red", "azul")]
    y = 130
    for nom, txt, est in ops:
        boton(p, Rect(cx - 230, y, 460, 66), txt, est, nombre=nom, fuente=FUENTES["h3"])
        y += 84


def pantalla_lan(p):
    encabezado(p, f"{TITULOS[JUEGO_SEL]} · Partidas en red",
               "Las partidas creadas aparecen aquí solas")

    lista = Rect(40, 100, 560, 430)
    tarjeta(p, lista)
    texto(p, "Partidas disponibles", lista.x + 20, lista.y + 14, FUENTES["h3"])
    validas = CLAVES_LAN[JUEGO_SEL]
    hosts = [h for h in HOSTS_ENCONTRADOS if h[2] in validas]
    estado = ("Buscando" + "." * (int(time.time() * 3) % 4)) if BUSCANDO else f"{len(hosts)} encontrada(s)"
    texto(p, estado, lista.right - 20, lista.y + 20, FUENTES["chica"], C_SUAVE, derecha=True)
    p.linea(C_BORDE, (lista.x + 16, lista.y + 52), (lista.right - 16, lista.y + 52), 1)

    if not hosts:
        texto(p, "No hay partidas creadas por ahora.", lista.centerx, lista.y + 170,
              FUENTES["normal"], C_SUAVE, centro=True)
        texto(p, "Crea una tú, o espera: la lista se actualiza sola.", lista.centerx,
              lista.y + 200, FUENTES["chica"], C_SUAVE, centro=True)
        texto(p, "Los dos deben estar en la misma WiFi, o uno conectado", lista.centerx,
              lista.y + 250, FUENTES["chica"], C_SUAVE, centro=True)
        texto(p, "al punto de acceso (hotspot) del otro celular.", lista.centerx,
              lista.y + 272, FUENTES["chica"], C_SUAVE, centro=True)
    y = lista.y + 64
    for ip, nom, clave in hosts[:6]:
        r = Rect(lista.x + 16, y, lista.w - 32, 52)
        sel = (ip == HOST_SELECC)
        p.rect((52, 82, 70) if sel else C_CARD2, r, 10)
        p.rect(C_ACENTO if sel else C_BORDE, r, 10, borde=2 if sel else 1)
        texto(p, nom, r.x + 16, r.y + 6, FUENTES["normal_b"], max_w=260)
        texto(p, ip, r.x + 16, r.y + 29, FUENTES["chica"], C_SUAVE)
        texto(p, ETQ_CLAVE.get(clave, clave), r.right - 16, r.y + 8, FUENTES["chica"],
              C_ACENTO if sel else C_SUAVE, derecha=True)
        texto(p, "Seleccionada" if sel else "Toca para elegir", r.right - 16, r.y + 29,
              FUENTES["chica"], C_ACENTO if sel else C_SUAVE, derecha=True)
        RECTS[f"host:{ip}"] = r
        y += 60

    bx, y = 630, 100
    if JUEGO_SEL == "ajedrez":
        boton(p, Rect(bx, y, 278, 52), "Crear partida · 2 jugadores", "primario",
              nombre="crear2", fuente=FUENTES["normal_b"])
        y += 62
        boton(p, Rect(bx, y, 278, 52), "Crear partida · 4 jugadores", "dorado",
              nombre="crear4", fuente=FUENTES["normal_b"])
        y += 62
    else:
        boton(p, Rect(bx, y, 278, 52), "Crear partida", "primario", nombre="crear2",
              fuente=FUENTES["normal_b"])
        y += 62
    boton(p, Rect(bx, y, 278, 52), "Buscar partidas", "azul", nombre="buscar",
          fuente=FUENTES["normal_b"])
    y += 62
    boton(p, Rect(bx, y, 278, 52), "Unirse a la seleccionada", "morado",
          activo=HOST_SELECC is not None, nombre="unirse", fuente=FUENTES["normal_b"])
    y += 70

    caja = Rect(bx, y, 278, 170)
    tarjeta(p, caja)
    texto(p, "¿No aparece? Conéctate por IP:", caja.x + 14, caja.y + 10, FUENTES["chica"],
          C_SUAVE, max_w=caja.w - 20)
    campo(p, Rect(caja.x + 14, caja.y + 38, caja.w - 28, 40), IP_TEXTO, "campo_ip", "192.168.43.1")
    boton(p, Rect(caja.x + 14, caja.y + 96, caja.w - 28, 54), "Conectar por IP", "gris",
          activo=bool(IP_TEXTO.strip()), nombre="ip_ok")

    if MENSAJE_ESTADO:
        texto(p, MENSAJE_ESTADO, W // 2, 560, FUENTES["normal"], C_AVISO, centro=True, max_w=W - 40)


def pantalla_esperando(p):
    encabezado(p, "Partida creada", TITULOS.get(HOST_CLAVE, ""), volver=False)
    caja = Rect(144, 100, 660, 430)
    tarjeta(p, caja)
    puntos = "." * (int(time.time() * 2) % 4)
    texto(p, "Esperando que un jugador se una" + puntos, caja.centerx, caja.y + 22,
          FUENTES["h3"], centro=True)
    texto(p, f"Tu nombre: {nombre_local()}   ·   Tu IP: {IP_LOCAL}", caja.centerx,
          caja.y + 60, FUENTES["chica"], C_SUAVE, centro=True, max_w=caja.w - 30)
    p.linea(C_BORDE, (caja.x + 24, caja.y + 94), (caja.right - 24, caja.y + 94), 1)
    inv = list(INVITACION_ENTRANTE)
    if not inv:
        texto(p, "Nadie ha pedido unirse todavía.", caja.centerx, caja.y + 190,
              FUENTES["normal"], C_SUAVE, centro=True)
        texto(p, "El otro jugador debe estar en tu misma WiFi o conectado a tu hotspot.",
              caja.centerx, caja.y + 225, FUENTES["chica"], C_SUAVE, centro=True,
              max_w=caja.w - 30)
    y = caja.y + 110
    for i, (_, nom) in enumerate(inv[:4]):
        r = Rect(caja.x + 24, y, caja.w - 48, 62)
        p.rect(C_CARD2, r, 10)
        p.rect(C_BORDE, r, 10, borde=1)
        texto(p, f"{nom} quiere jugar", r.x + 16, r.centery - 12, FUENTES["normal_b"], max_w=240)
        boton(p, Rect(r.right - 236, r.y + 11, 108, 40), "Aceptar", "primario",
              nombre=f"acc:{i}", fuente=FUENTES["normal"])
        boton(p, Rect(r.right - 120, r.y + 11, 108, 40), "Rechazar", "rojo",
              nombre=f"rej:{i}", fuente=FUENTES["normal"])
        y += 72
    boton(p, Rect(W // 2 - 150, 566, 300, 50), "Cancelar y volver", "gris", nombre="cancelar")


def pantalla_lobby4(p):
    encabezado(p, "Ajedrez · 4 jugadores", "Sala de espera", volver=False)
    caja = Rect(144, 100, 660, 430)
    tarjeta(p, caja)
    if ES_HOST4:
        texto(p, f"Tu IP: {IP_LOCAL}  ·  pueden unirse hasta 3 jugadores más", caja.centerx,
              caja.y + 18, FUENTES["chica"], C_SUAVE, centro=True, max_w=caja.w - 30)
    else:
        puntos = "." * (int(time.time() * 2) % 4)
        texto(p, "Esperando a que el host inicie la partida" + puntos, caja.centerx,
              caja.y + 16, FUENTES["normal"], C_SUAVE, centro=True)
    y = caja.y + 56
    for s in range(4):
        r = Rect(caja.x + 24, y, caja.w - 48, 62)
        p.rect(C_CARD2, r, 10)
        p.rect(COL_ASIENTO[s], r, 10, borde=2)
        p.circulo(COL_ASIENTO[s], (r.x + 34, r.centery), 18)
        nom = LOBBY[s]
        if nom:
            extra = "  (tú)" if s == MI_ASIENTO else ""
            texto(p, nom + extra, r.x + 70, r.centery - 12, FUENTES["normal_b"], max_w=300)
            texto(p, NOM_ASIENTO[s], r.right - 16, r.centery - 10, FUENTES["chica"],
                  C_SUAVE, derecha=True)
        else:
            texto(p, "Esperando jugador…", r.x + 70, r.centery - 12, FUENTES["normal"], C_SUAVE)
        y += 70
    ocupados = sum(1 for n in LOBBY if n)
    if ES_HOST4:
        boton(p, Rect(W // 2 - 300, 566, 280, 50), "Iniciar partida", "primario",
              activo=ocupados >= 2, nombre="iniciar4")
        boton(p, Rect(W // 2 + 20, 566, 280, 50), "Cancelar y volver", "gris", nombre="cancelar")
    else:
        boton(p, Rect(W // 2 - 150, 566, 300, 50), "Salir de la sala", "gris", nombre="cancelar")


def pantalla_conectando(p):
    encabezado(p, "Conectando", None, volver=False)
    caja = Rect(184, 170, 580, 250)
    tarjeta(p, caja)
    texto(p, "Un momento" + "." * (int(time.time() * 2) % 4), caja.centerx, caja.y + 50,
          FUENTES["h2"], centro=True)
    texto(p, MENSAJE_ESTADO, caja.centerx, caja.y + 110, FUENTES["normal"], C_SUAVE,
          centro=True, max_w=caja.w - 40)
    boton(p, Rect(caja.centerx - 130, caja.y + 160, 260, 52), "Cancelar", "gris",
          nombre="cancelar")


def pantalla_cargando(p):
    encabezado(p, "Preparando la IA", None, volver=False)
    caja = Rect(184, 170, 580, 250)
    tarjeta(p, caja)
    texto(p, "Cargando" + "." * (int(time.time() * 2) % 4), caja.centerx, caja.y + 50,
          FUENTES["h2"], centro=True)
    texto(p, CARGANDO_MSG, caja.centerx, caja.y + 110, FUENTES["normal"], C_SUAVE,
          centro=True, max_w=caja.w - 40)
    boton(p, Rect(caja.centerx - 130, caja.y + 160, 260, 52), "Cancelar", "gris",
          nombre="cancelar")


def color_nivel(i):
    t = i / max(1, len(NIVELES) - 1)
    a, b = (62, 150, 90), (176, 66, 66)
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


def pantalla_nivel(p):
    encabezado(p, "Elige la dificultad",
               "Empieza por los niveles bajos: se aprende jugando")
    cw, ch, gap = 280, 76, 20
    x0 = (W - (3 * cw + 2 * gap)) // 2
    for i, (elo, titulo, sub, _) in enumerate(NIVELES):
        col, fila = i % 3, i // 3
        r = Rect(x0 + col * (cw + gap), 108 + fila * (ch + 14), cw, ch)
        c = color_nivel(i)
        p.rect((12, 14, 20), r.move(0, 3), 12)
        p.rect(c, r, 12)
        p.rect(aclarar(c, 30), r, 12, borde=1)
        texto(p, titulo, r.centerx, r.y + 12, FUENTES["h3"], centro=True)
        texto(p, sub, r.centerx, r.y + 44, FUENTES["chica"], (240, 240, 240), centro=True)
        RECTS[f"nivel:{i}"] = r
    if MENSAJE_ESTADO:
        texto(p, MENSAJE_ESTADO, W // 2, 600, FUENTES["normal"], C_AVISO, centro=True, max_w=W - 40)


# ---------- pantalla de juego ----------
def chip_jugador(p, cx, cy, lado, clave):
    p.circulo((200, 200, 200), (cx, cy), 20)
    if clave == "tresenraya":
        p.circulo((40, 46, 62), (cx, cy), 18)
        texto(p, "XO"[lado], cx, cy - 13, FUENTES["h3"], C_TEXTO, centro=True)
    else:
        p.circulo((250, 250, 250) if lado == 0 else (28, 28, 32), (cx, cy), 18)


def tarjeta_jugador(p, rect, nombre, sub, lado, activo):
    tarjeta(p, rect, C_CARD, C_ACENTO if activo else C_BORDE)
    chip_jugador(p, rect.x + 34, rect.centery, lado, juego.clave)
    texto(p, nombre, rect.x + 64, rect.y + 10, FUENTES["normal_b"], max_w=rect.w - 76)
    texto(p, sub, rect.x + 64, rect.y + 36, FUENTES["chica"], C_SUAVE, max_w=rect.w - 76)


def panel_jugadas(p, rect):
    tarjeta(p, rect)
    texto(p, "Jugadas", rect.x + 16, rect.y + 10, FUENTES["normal_b"])
    p.linea(C_BORDE, (rect.x + 12, rect.y + 38), (rect.right - 12, rect.y + 38), 1)
    filas = juego.jugadas()
    visibles = max(1, (rect.h - 48) // 22)
    y = rect.y + 44
    for n, a, b in filas[-visibles:]:
        texto(p, f"{n}.", rect.x + 16, y, FUENTES["chica"], C_SUAVE)
        texto(p, a, rect.x + 54, y, FUENTES["chica"], C_TEXTO, max_w=100)
        texto(p, b, rect.x + 158, y, FUENTES["chica"], C_TEXTO, max_w=100)
        y += 22


def banner_fin(p):
    area = Rect(BX, BY + 8 * TAM // 2 - 78, 8 * TAM, 156)
    p.rect((10, 12, 18, 225), area)
    texto(p, MENSAJE_ESTADO, area.centerx, area.y + 30, FUENTES["h2"], C_AVISO, centro=True,
          max_w=area.w - 30)
    if MODO == "lan":
        sub = "Revancha: los colores se intercambian"
    else:
        sub = "Usa los botones de la derecha para continuar"
    texto(p, sub, area.centerx, area.y + 96, FUENTES["chica"], C_SUAVE, centro=True)


def dibujar_botones_panel(p, botones):
    """botones: [(nombre, texto, estilo, activo)] -> se apilan desde abajo."""
    h, gap, fondo = 38, 6, 552
    y = fondo - len(botones) * (h + gap) + gap
    top = y
    for nom, txt, est, act in botones:
        boton(p, Rect(PX, y, PW, h), txt, est, activo=act, nombre=nom)
        y += h + gap
    return top


def pantalla_juego2(p):
    juego.interactivo = puede_mover()
    juego.dibujar(p)

    top = (1 - MI_LADO) if MODO in ("lan", "ia") else 1
    bot = 1 - top
    activo_turno = ESTADO == "JUEGO"
    if MODO == "ia":
        sub_top = f"{juego.lados[top]} · {ia.etiqueta}"
    elif MODO == "lan":
        sub_top = f"{juego.lados[top]} · Jugador en red"
    else:
        sub_top = f"{juego.lados[top]} · mismo celular"
    tarjeta_jugador(p, Rect(PX, 20, PW, 66), NOMBRE_RIVAL or "Rival", sub_top, top,
                    activo_turno and juego.turno == top)

    est = Rect(PX, 96, PW, 44)
    tarjeta(p, est, C_CARD2)
    if ESTADO == "FIN":
        msg, col = "Partida terminada", C_AVISO
    elif MODO == "ia" and ia.pensando:
        msg, col = "La IA está pensando" + "." * (int(time.time() * 3) % 4), C_SUAVE
    elif MODO == "local":
        msg, col = f"Turno de {juego.lados[juego.turno]}", C_ACENTO
    elif juego.turno == MI_LADO:
        msg, col = "Tu turno", C_ACENTO
    else:
        msg, col = "Turno del rival", C_SUAVE
    texto(p, msg, est.centerx, est.centery - 11, FUENTES["normal_b"], col, centro=True,
          max_w=PW - 16)

    botones = []
    if MODO == "ia":
        botones = [("g_elo", "Seleccionar nivel", "morado", True),
                   ("g_rehacer", "Deshacer jugada", "azul",
                    (not ia.pensando) and bool(juego.board.move_stack)),
                   ("g_reiniciar", "Reiniciar partida", "primario", True)]
    elif MODO == "local":
        botones = [("g_reiniciar", "Reiniciar partida", "primario", True)]
    elif MODO == "lan" and ESTADO == "FIN":
        if REV_PROPIA:
            botones = [("g_revancha", "Esperando al rival…", "gris", False)]
        elif REV_RIVAL:
            botones = [("g_revancha", "Aceptar revancha", "primario", True)]
        else:
            botones = [("g_revancha", "Pedir revancha", "primario", True)]
    botones.append(("g_menu", "Menú principal", "rojo", True))
    top_btn = dibujar_botones_panel(p, botones)

    panel_jugadas(p, Rect(PX, 150, PW, max(80, top_btn - 160)))

    if MODO == "local":
        sub_yo = f"{juego.lados[bot]} · mismo celular"
    else:
        sub_yo = juego.lados[bot]
    tarjeta_jugador(p, Rect(PX, 562, PW, 66), nombre_local(), sub_yo, bot,
                    activo_turno and juego.turno == bot)
    if ESTADO == "FIN":
        banner_fin(p)


def nombre_para_asiento(s):
    if MODO == "lan4" and LOBBY[s]:
        return LOBBY[s]
    return NOM_ASIENTO[s]


def pantalla_juego4(p):
    j4.interactivo = True
    j4.dibujar(p)
    for s in range(4):
        r = Rect(PX, 20 + s * 60, PW, 54)
        presente = s in j4.activos
        activo = ESTADO == "JUEGO" and presente and s == j4.turno_asiento
        tarjeta(p, r, C_CARD if presente else C_CARD2, COL_ASIENTO[s] if activo else C_BORDE)
        p.circulo(COL_ASIENTO[s] if (presente and s in j4.vivos) else (90, 90, 90),
                  (r.x + 30, r.centery), 15)
        if presente:
            nom = nombre_para_asiento(s)
            if MODO == "lan4" and s == MI_ASIENTO:
                nom += " (tú)"
            sub = "Eliminado" if s not in j4.vivos else ("Mueve ahora" if activo else "En juego")
        else:
            nom, sub = NOM_ASIENTO[s], "No participa"
        texto(p, nom, r.x + 56, r.y + 6, FUENTES["normal_b"], max_w=r.w - 66)
        texto(p, sub, r.x + 56, r.y + 29, FUENTES["chica"], C_AVISO if activo else C_SUAVE)

    est = Rect(PX, 266, PW, 44)
    tarjeta(p, est, C_CARD2)
    if ESTADO == "FIN":
        msg, col = "Partida terminada", C_AVISO
    elif MODO == "lan4":
        if j4.turno_asiento == MI_ASIENTO:
            msg, col = "Tu turno", C_ACENTO
        else:
            msg, col = f"Turno de {nombre_para_asiento(j4.turno_asiento)}", C_SUAVE
    else:
        msg, col = f"Turno de {NOM_ASIENTO[j4.turno_asiento]}", COL_ASIENTO[j4.turno_asiento]
    texto(p, msg, est.centerx, est.centery - 11, FUENTES["normal_b"], col, centro=True,
          max_w=PW - 16)

    info = Rect(PX, 320, PW, 140)
    tarjeta(p, info, C_CARD2)
    lineas = ["Pierde quien pierde su rey.", "Gana el último con rey.",
              "Casilla roja = tu rey en peligro.", "Peón: llega a la línea 11 y corona."]
    if MODO == "local4":
        lineas[3] = "El tablero gira para quien mueve."
    for i, l in enumerate(lineas):
        texto(p, l, info.x + 14, info.y + 12 + i * 29, FUENTES["chica"], C_SUAVE, max_w=PW - 24)

    botones = []
    if MODO == "local4":
        botones.append(("g_reiniciar", "Reiniciar partida", "primario", True))
    elif ESTADO == "FIN":
        if ES_HOST4:
            botones.append(("g_nueva4", "Nueva partida (rotan colores)", "primario", True))
        else:
            botones.append(("g_x", "Espera al host…", "gris", False))
    botones.append(("g_menu", "Menú principal", "rojo", True))
    dibujar_botones_panel(p, botones)

    if ESTADO == "FIN":
        area = Rect(j4.ox, j4.oy + 14 * j4.T // 2 - 70, 14 * j4.T, 140)
        p.rect((10, 12, 18, 225), area)
        texto(p, MENSAJE_ESTADO, area.centerx, area.y + 50, FUENTES["h2"], C_AVISO,
              centro=True, max_w=area.w - 30)


def pantalla_juego(p):
    if MODO in ("lan4", "local4"):
        pantalla_juego4(p)
    else:
        pantalla_juego2(p)


def modal_confirmar(p):
    p.rect((0, 0, 0, 170), (0, 0, W, H))
    for k in list(RECTS):
        if not k.startswith("_"):
            del RECTS[k]
    caja = Rect(W // 2 - 260, H // 2 - 120, 520, 240)
    tarjeta(p, caja, C_CARD, C_BORDE, 16)
    if CONFIRMAR == "menu":
        t1, t2 = "¿Volver al menú principal?", "Se perderá la partida actual."
    elif CONFIRMAR == "elo":
        t1, t2 = "¿Cambiar el nivel de dificultad?", "Se perderá la partida actual."
    else:
        t1, t2 = "¿Reiniciar la partida?", "Empezarás de nuevo desde cero."
    texto(p, t1, caja.centerx, caja.y + 36, FUENTES["h2"], centro=True, max_w=caja.w - 30)
    texto(p, t2, caja.centerx, caja.y + 92, FUENTES["normal"], C_SUAVE, centro=True)
    boton(p, Rect(caja.x + 30, caja.bottom - 78, 210, 50), "Sí", "rojo", nombre="conf_si")
    boton(p, Rect(caja.right - 240, caja.bottom - 78, 210, 50), "No, seguir", "gris",
          nombre="conf_no")


def dibujar_todo(p):
    p.fondo_degradado(FONDO_TEX)
    if ESTADO in ("JUEGO", "FIN"):
        pantalla_juego(p)
    elif ESTADO == "SUBMENU":
        pantalla_submenu(p)
    elif ESTADO == "LAN":
        pantalla_lan(p)
    elif ESTADO == "ESPERANDO":
        pantalla_esperando(p)
    elif ESTADO == "LOBBY4":
        pantalla_lobby4(p)
    elif ESTADO == "CONECTANDO":
        pantalla_conectando(p)
    elif ESTADO == "CARGANDO_IA":
        pantalla_cargando(p)
    elif ESTADO == "NIVEL":
        pantalla_nivel(p)
    else:
        pantalla_menu(p)


# ============================================================
# ACCIONES (toques y botón "atrás")
# ============================================================
def pedir_texto(titulo, inicial, max_len, permitido, al_aceptar):
    """Ventana con el teclado del celular para escribir el nombre o la IP."""
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput

    caja = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
    ti = TextInput(text=inicial, multiline=False, font_size=dp(22), size_hint_y=None,
                   height=dp(52), write_tab=False)

    def limitar(inst, val):
        v = "".join(ch for ch in val if ch in permitido) if permitido else val
        v = v[:max_len]
        if v != val:
            inst.text = v
    ti.bind(text=limitar)

    pop = Popup(title=titulo, content=caja, size_hint=(0.8, None), height=dp(210),
                pos_hint={"center_x": 0.5, "top": 0.97})

    def aceptar(*_):
        try:
            al_aceptar(ti.text)
        finally:
            pop.dismiss()

    ti.bind(on_text_validate=aceptar)
    fila = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
    fila.add_widget(Button(text="Cancelar", on_release=lambda *_: pop.dismiss()))
    fila.add_widget(Button(text="Aceptar", on_release=aceptar))
    caja.add_widget(ti)
    caja.add_widget(fila)
    pop.open()
    Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.3)


def _fijar_nombre(v):
    global NOMBRE_LOCAL
    NOMBRE_LOCAL = v.strip()[:16] or "Jugador"
    guardar_nombre()


def _fijar_ip(v):
    global IP_TEXTO
    IP_TEXTO = v.strip()


def pedir_salida(tipo):
    global CONFIRMAR
    if ESTADO == "JUEGO":
        CONFIRMAR = tipo
    else:
        ejecutar_salida(tipo)


def ejecutar_salida(tipo):
    global CONFIRMAR
    CONFIRMAR = None
    if tipo == "menu":
        volver_menu()
    elif tipo == "elo":
        volver_elo()
    else:
        reiniciar_partida()


def accion(n):
    global SALIR, HOST_SELECC, CONFIRMAR, JUEGO_SEL, CARGANDO_MSG

    if n == "conf_si":
        ejecutar_salida(CONFIRMAR)
        return
    if n == "conf_no":
        CONFIRMAR = None
        return
    if n == "campo_nombre":
        pedir_texto("Tu nombre", NOMBRE_LOCAL, 16, None, _fijar_nombre)
        return
    if n == "campo_ip":
        pedir_texto("IP del que creó la partida", IP_TEXTO, 15, "0123456789.", _fijar_ip)
        return

    if ESTADO == "MENU":
        if n in ("m_ajedrez", "m_damas", "m_3r"):
            JUEGO_SEL = {"m_ajedrez": "ajedrez", "m_damas": "damas", "m_3r": "tresenraya"}[n]
            ir("SUBMENU")
        elif n == "m_salir":
            SALIR = True

    elif ESTADO == "SUBMENU":
        if n == "volver":
            ir("MENU")
        elif n == "s_ia":
            ir("NIVEL")
        elif n == "s_local":
            empezar_local()
        elif n == "s_local4":
            empezar_local4()
        elif n == "s_lan":
            ir_lan()

    elif ESTADO == "LAN":
        if n == "volver":
            ir("SUBMENU")
        elif n == "crear2":
            crear_partida(JUEGO_SEL)
        elif n == "crear4":
            crear_partida("ajedrez4")
        elif n == "buscar":
            lanzar_busqueda()
        elif n == "unirse" and HOST_SELECC:
            unirse(HOST_SELECC)
        elif n == "ip_ok":
            unirse(IP_TEXTO)
        elif n.startswith("host:"):
            HOST_SELECC = n[5:]

    elif ESTADO == "ESPERANDO":
        if n == "cancelar":
            cerrar_conexiones()
            ir_lan()
        elif n.startswith("acc:"):
            aceptar_invitacion(int(n[4:]))
        elif n.startswith("rej:"):
            rechazar_invitacion(int(n[4:]))

    elif ESTADO == "LOBBY4":
        if n == "cancelar":
            cerrar_conexiones()
            ir_lan()
        elif n == "iniciar4" and ES_HOST4:
            iniciar4_host()

    elif ESTADO == "CONECTANDO":
        if n == "cancelar":
            cerrar_conexiones()
            ir_lan()

    elif ESTADO == "CARGANDO_IA":
        if n == "cancelar":
            ia.cerrar()
            ir("NIVEL")

    elif ESTADO == "NIVEL":
        if n == "volver":
            ir("SUBMENU")
        elif n.startswith("nivel:"):
            idx = int(n[6:])
            ia.cargar(idx)
            CARGANDO_MSG = f"Preparando «{NIVELES[idx][1]}»..."
            ir("CARGANDO_IA")

    elif ESTADO in ("JUEGO", "FIN"):
        if n == "g_menu":
            pedir_salida("menu")
        elif n == "g_elo":
            pedir_salida("elo")
        elif n == "g_reiniciar":
            pedir_salida("reiniciar")
        elif n == "g_rehacer":
            rehacer_jugada()
        elif n == "g_revancha":
            pedir_revancha()
        elif n == "g_nueva4" and ES_HOST4:
            nueva4_host()


def manejar_clic(pos):
    if RECTS.get("_estado") != (ESTADO, CONFIRMAR):
        return
    for nombre, r in list(RECTS.items()):
        if nombre.startswith("_"):
            continue
        if r.collidepoint(pos):
            accion(nombre)
            return
    if CONFIRMAR is None and ESTADO == "JUEGO":
        clic_tablero(pos)


def atras():
    """Botón 'atrás' de Android (o Esc). Devuelve False si hay que cerrar la app."""
    global CONFIRMAR
    if CONFIRMAR:
        CONFIRMAR = None
    elif ESTADO == "MENU":
        return False
    elif ESTADO == "SUBMENU":
        ir("MENU")
    elif ESTADO in ("LAN", "NIVEL"):
        ir("SUBMENU")
    elif ESTADO in ("ESPERANDO", "LOBBY4", "CONECTANDO"):
        cerrar_conexiones()
        ir_lan()
    elif ESTADO == "CARGANDO_IA":
        ia.cerrar()
        ir("NIVEL")
    elif ESTADO == "JUEGO":
        CONFIRMAR = "menu"
    elif ESTADO == "FIN":
        volver_menu()
    return True


# ============================================================
# APLICACIÓN KIVY
# ============================================================
def limpiar_todo():
    try:
        cerrar_conexiones()
    except Exception:
        pass
    try:
        if ia:
            ia.cerrar(sincrono=False)
    except Exception:
        pass
    liberar_android()


def crear_fondo_tex():
    tex = Texture.create(size=(1, 2), colorfmt="rgb")
    datos = bytes(C_BG2) + bytes(C_BG1)          # fila 0 = abajo
    tex.blit_buffer(datos, colorfmt="rgb", bufferfmt="ubyte")
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    return tex


class Lienzo(Widget):
    """Un solo widget que dibuja todo el juego en un lienzo virtual de 948x648,
    escalado y centrado en la pantalla (sirve para cualquier tamaño de celular)."""

    def _transformacion(self):
        s = min(self.width / float(W), self.height / float(H))
        ox = self.x + (self.width - W * s) / 2.0
        oy = self.y + (self.height - H * s) / 2.0
        return s, ox, oy

    def a_virtual(self, pos):
        s, ox, oy = self._transformacion()
        if s <= 0:
            return None
        return int((pos[0] - ox) / s), int(H - (pos[1] - oy) / s)

    def on_touch_down(self, touch):
        if getattr(touch, "is_mouse_scrolling", False):
            return False
        try:
            v = self.a_virtual(touch.pos)
            if v is not None:
                manejar_clic(v)
        except Exception:
            traceback.print_exc()
        return True

    def redibujar(self):
        s, ox, oy = self._transformacion()
        G.esc = s
        self.canvas.clear()
        with self.canvas:
            Color(0.078, 0.094, 0.133, 1)
            Rectangle(pos=self.pos, size=self.size)
            PushMatrix()
            Translate(ox, oy)
            Scale(s, s, 1)
            RECTS.clear()
            dibujar_todo(G)
            if CONFIRMAR is not None and ESTADO == "JUEGO":
                modal_confirmar(G)
            RECTS["_estado"] = (ESTADO, CONFIRMAR)
            PopMatrix()


class JuegosApp(App):
    title = "Juegos de mesa"

    def build(self):
        global CARPETA_DATOS, ARCHIVO_CONFIG, RES, G, JUEGOS, juego, j4, ia
        global IMG_MENU, FONDO_TEX, FALTAN

        try:
            CARPETA_DATOS = self.user_data_dir
            ARCHIVO_CONFIG = os.path.join(CARPETA_DATOS, "config.json")
        except Exception:
            pass
        cargar_nombre()
        if not ANDROID:
            Window.size = (948, 648)
        Window.clearcolor = (0.078, 0.094, 0.133, 1)
        Window.bind(on_keyboard=self.al_teclado)

        RES = Recursos([DIR_BASE, os.getcwd()])
        G = Gfx(W, H)
        FONDO_TEX = crear_fondo_tex()

        ctx = SimpleNamespace(
            rect=Rect(BX, BY, 8 * TAM, 8 * TAM), F=FUENTES,
            cargar=RES.cargar, cargar_fit=RES.cargar_fit,
            colores_tablero=COLORES_TABLERO, C_BORDE=C_BORDE, dir_base=DIR_BASE)
        JUEGOS = {"ajedrez": Ajedrez(ctx), "damas": Damas(ctx), "tresenraya": TresEnRaya(ctx)}
        juego = JUEGOS["ajedrez"]
        j4 = Ajedrez4(ctx)
        ia = GestorIA(DIR_BASE)

        dama_blanca = (RES.cargar_fit("peon_blanco_dama.png", 112, 112)
                       or RES.cargar_fit("peon_dama_blanca.png", 112, 112))
        IMG_MENU = {"ajedrez": RES.cargar_fit("w_Caballo.png", 112, 112),
                    "damas": dama_blanca,
                    "tresenraya": lambda p, x, y: dib_mini3r(p, x, y, 112)}
        FALTAN = imagenes_faltantes()
        if FALTAN:
            print("AVISO: faltan imágenes:", ", ".join(FALTAN))

        preparar_android()
        threading.Thread(target=hilo_respondedor_udp, daemon=True).start()

        self.lienzo = Lienzo()
        Clock.schedule_interval(self.tick, 1.0 / 30.0)
        return self.lienzo

    def al_teclado(self, ventana, tecla, *args):
        if tecla == 27:                       # atrás / Esc
            try:
                return atras()
            except Exception:
                traceback.print_exc()
                return True
        return False

    def tick(self, dt):
        global ERRORES, SALIR
        try:
            procesar_cola()
            if ESTADO == "LAN" and not BUSCANDO and time.time() - ULTIMA_BUSQ > 2.5:
                lanzar_busqueda()

            if ESTADO == "CARGANDO_IA":
                if ia.estado_carga == "ok":
                    ia.tomar_carga()
                    empezar_ia()
                elif ia.estado_carga == "error":
                    ia.estado_carga = None
                    ir("NIVEL", "No se pudo preparar la IA. Intenta de nuevo.")

            if ESTADO == "JUEGO" and MODO == "ia":
                mv = ia.tomar_jugada()
                if mv is not None:
                    juego.aplicar(mv.uci())
                    comprobar_fin()

            self.lienzo.redibujar()
            ERRORES = 0
        except Exception:
            traceback.print_exc()
            ERRORES += 1
            if ERRORES >= 3:                  # algo está roto: vuelve al menú en vez de cerrarse
                ERRORES = 0
                try:
                    volver_menu()
                    ir("MENU", "Ocurrió un error y se reinició la pantalla.")
                except Exception:
                    traceback.print_exc()
        if SALIR:
            SALIR = False
            self.stop()

    def on_pause(self):
        return True                           # permite volver a la app sin que se reinicie

    def on_resume(self):
        pass

    def on_stop(self):
        limpiar_todo()


def imagenes_faltantes():
    nombres = ["w_Peon.png", "w_Caballo.png", "w_Alfil.png", "w_Torre.png", "w_Dama.png",
               "w_Rey.png", "b_Peon.png", "b_Caballo.png", "b_Alfil.png", "b_Torre.png",
               "b_Dama.png", "b_Rey.png", "peon_blanco.png", "peon_negro.png",
               "peon_negro_dama.png", "tablero_3_en_raya.png", "equis_3_en_raya.png",
               "circulo_3_en_raya.png"]
    falta = [n for n in nombres if RES.buscar(n) is None]
    if RES.buscar("peon_blanco_dama.png") is None and RES.buscar("peon_dama_blanca.png") is None:
        falta.append("peon_blanco_dama.png")
    return falta


if __name__ == "__main__":
    JuegosApp().run()
