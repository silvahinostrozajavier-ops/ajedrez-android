# juego_ajedrez.py — Ajedrez (2 jugadores), motor de IA (Texel / Stockfish) y
#                    Ajedrez de 4 jugadores.
import os
import random
import threading
import time

import chess
try:
    import chess.engine
    HAY_UCI = True
except Exception:                       # sin soporte de motores externos: se usa la IA integrada
    HAY_UCI = False

from gfx import Rect

ARCHIVOS_PIEZAS = {
    "P": "w_Peon.png",   "N": "w_Caballo.png", "B": "w_Alfil.png",
    "R": "w_Torre.png",  "Q": "w_Dama.png",    "K": "w_Rey.png",
    "p": "b_Peon.png",   "n": "b_Caballo.png", "b": "b_Alfil.png",
    "r": "b_Torre.png",  "q": "b_Dama.png",    "k": "b_Rey.png",
}

# (ELO objetivo, título, subtítulo, probabilidad de jugada "distraída")
# La probabilidad hace que los niveles bajos fallen a propósito para que los
# niños jueguen, aprendan y no se frustren. Puedes cambiarla.
ELO_STOCKFISH = 3000
NIVELES = [
    (50,   "Nivel 0-100",     "Primeros pasos",  0.60),
    (150,  "Nivel 100-200",   "Aprendiz",        0.50),
    (300,  "Nivel 200-400",   "Principiante",    0.40),
    (500,  "Nivel 400-600",   "Principiante +",  0.28),
    (700,  "Nivel 600-800",   "Casual",          0.18),
    (900,  "Nivel 800-1000",  "Casual +",        0.10),
    (1100, "Nivel 1000-1200", "Jugador de club", 0.05),
    (1350, "Nivel 1200-1500", "Intermedio",      0.0),
    (1650, "Nivel 1500-1800", "Intermedio +",    0.0),
    (1900, "Nivel 1800-2000", "Avanzado",        0.0),
    (2100, "Nivel 2000-2200", "Experto",         0.0),
    (2370, "Nivel 2200-2540", "Maestro",         0.0),
    (ELO_STOCKFISH, "Stockfish", "Máximo nivel", 0.0),
]

NOMBRES_PROMO = {chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B", chess.KNIGHT: "N"}


# ============================================================
# AJEDREZ 2 JUGADORES
# ============================================================
class Ajedrez:
    clave = "ajedrez"
    titulo = "Ajedrez"
    lados = ("Blancas", "Negras")

    def __init__(self, ctx):
        self.ctx = ctx
        self.T = ctx.rect.w // 8
        self.ox = ctx.rect.x + (ctx.rect.w - 8 * self.T) // 2
        self.oy = ctx.rect.y + (ctx.rect.h - 8 * self.T) // 2
        self.img = {s: ctx.cargar_fit(a, self.T, self.T) for s, a in ARCHIVOS_PIEZAS.items()}
        self.interactivo = False
        self.nueva()

    def nueva(self, mi_lado=0, orientar=False):
        self.board = chess.Board()
        self.mi_lado = mi_lado
        self.volteo = bool(orientar and mi_lado == 1)
        self.sel = None
        self.legales = []
        self.promo = None
        self._san = (-1, None, [])

    @property
    def turno(self):
        return 0 if self.board.turn == chess.WHITE else 1

    # ---------- coordenadas ----------
    def _px(self, cas):
        col, fila = chess.square_file(cas), 7 - chess.square_rank(cas)
        if self.volteo:
            col, fila = 7 - col, 7 - fila
        return self.ox + col * self.T, self.oy + fila * self.T

    def _cas(self, pos):
        x, y = pos[0] - self.ox, pos[1] - self.oy
        if x < 0 or y < 0:
            return None
        col, fila = x // self.T, y // self.T
        if not (0 <= col < 8 and 0 <= fila < 8):
            return None
        if self.volteo:
            col, fila = 7 - col, 7 - fila
        return chess.square(int(col), int(7 - fila))

    # ---------- jugadas ----------
    def _jugar(self, mv):
        self.board.push(mv)
        self.sel, self.legales, self.promo = None, [], None
        return mv.uci()

    def clic(self, pos):
        if self.promo:
            elegido = self._promo_en(pos)
            desde, hasta = self.promo
            self.promo = None
            if elegido is not None:
                mv = chess.Move(desde, hasta, promotion=elegido)
                if mv in self.board.legal_moves:
                    return self._jugar(mv)
            self.sel, self.legales = None, []
            return None
        cas = self._cas(pos)
        if cas is None:
            return None
        if self.sel is not None:
            cands = [m for m in self.legales if m.to_square == cas]
            if cands:
                if cands[0].promotion is not None:
                    self.promo = (self.sel, cas)       # el jugador elige la pieza
                    return None
                return self._jugar(cands[0])
        pieza = self.board.piece_at(cas)
        if pieza and pieza.color == self.board.turn:
            self.sel = cas
            self.legales = [m for m in self.board.legal_moves if m.from_square == cas]
        else:
            self.sel, self.legales = None, []
        return None

    def aplicar(self, uci):
        try:
            mv = chess.Move.from_uci(uci)
        except Exception:
            return
        if mv in self.board.legal_moves:
            self.board.push(mv)
            self.sel, self.legales, self.promo = None, [], None

    def deshacer(self):
        """Quita tu última jugada (y la respuesta de la IA)."""
        if not self.board.move_stack:
            return
        self.board.pop()
        if self.board.turn == chess.BLACK and self.board.move_stack:
            self.board.pop()
        self.sel, self.legales, self.promo = None, [], None

    def resultado(self):
        b = self.board
        if b.is_checkmate():
            return ("gana", 1 - self.turno, "Jaque mate")
        if b.is_stalemate():
            return ("tablas", None, "Tablas por ahogado")
        if b.is_insufficient_material():
            return ("tablas", None, "Tablas por material insuficiente")
        if b.is_seventyfive_moves():
            return ("tablas", None, "Tablas por regla de 75 movimientos")
        if b.is_fivefold_repetition():
            return ("tablas", None, "Tablas por repetición")
        return None

    def jugadas(self):
        n = len(self.board.move_stack)
        ult = self.board.move_stack[-1] if n else None
        if self._san[0] != n or self._san[1] != ult:
            tmp = chess.Board()
            sans = []
            for m in self.board.move_stack:
                try:
                    sans.append(tmp.san(m))
                    tmp.push(m)
                except Exception:
                    break
            self._san = (n, ult, sans)
        sans = self._san[2]
        return [(i // 2 + 1, sans[i], sans[i + 1] if i + 1 < len(sans) else "")
                for i in range(0, len(sans), 2)]

    # ---------- promoción ----------
    def _promo_rects(self):
        w = int(self.T * 1.15)
        total = 4 * w
        x0 = self.ox + (8 * self.T - total) // 2
        y0 = self.oy + (8 * self.T - w) // 2
        return [(pt, Rect(x0 + i * w, y0, w, w))
                for i, pt in enumerate((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT))]

    def _promo_en(self, pos):
        for pt, r in self._promo_rects():
            if r.collidepoint(pos):
                return pt
        return None

    # ---------- dibujo ----------
    def dibujar(self, p):
        T = self.T
        col = self.ctx.colores_tablero
        F = self.ctx.F["coord"]
        for fila in range(8):
            for c in range(8):
                clara = (fila + c) % 2 == 0
                x, y = self.ox + c * T, self.oy + fila * T
                p.rect(col[0 if clara else 1], (x, y, T, T))
                contra = col[1 if clara else 0]
                if c == 0:
                    rango = (fila + 1) if self.volteo else (8 - fila)
                    p.texto(str(rango), x + 3, y + 2, F, contra)
                if fila == 7:
                    arch = chess.FILE_NAMES[7 - c] if self.volteo else chess.FILE_NAMES[c]
                    p.texto(arch, x + T - 11, y + T - 16, F, contra)

        if self.board.move_stack:
            ult = self.board.move_stack[-1]
            for c in (ult.from_square, ult.to_square):
                x, y = self._px(c)
                p.rect((255, 226, 70, 100), (x, y, T, T))
        if self.board.is_check():
            rey = self.board.king(self.board.turn)
            if rey is not None:
                x, y = self._px(rey)
                p.circulo((220, 40, 40, 170), (x + T // 2, y + T // 2), T // 2)
        if self.sel is not None:
            x, y = self._px(self.sel)
            p.rect((90, 200, 90, 130), (x, y, T, T))

        for cas in chess.SQUARES:
            pieza = self.board.piece_at(cas)
            if pieza:
                x, y = self._px(cas)
                img = self.img.get(pieza.symbol())
                if img:
                    p.img(img, x + (T - img.get_width()) // 2, y + (T - img.get_height()) // 2)
                else:
                    p.texto(pieza.symbol(), x + T // 2, y + T // 5, self.ctx.F["h1"],
                            (0, 0, 0), centro=True)

        for mov in self.legales:
            x, y = self._px(mov.to_square)
            if self.board.piece_at(mov.to_square) is not None or self.board.is_en_passant(mov):
                p.circulo((40, 130, 40, 190), (x + T // 2, y + T // 2), T // 2 - 6, borde=5)
            else:
                p.circulo((40, 130, 40, 170), (x + T // 2, y + T // 2), 12)

        p.rect(self.ctx.C_BORDE, (self.ox - 1, self.oy - 1, 8 * T + 2, 8 * T + 2), borde=2)

        if self.promo:
            p.rect((0, 0, 0, 150), (self.ox, self.oy, 8 * T, 8 * T))
            p.texto("Elige la pieza", self.ox + 4 * T, self.oy + 4 * T - T * 1.15,
                    self.ctx.F["h3"], (255, 255, 255), centro=True)
            blanca = self.board.turn == chess.WHITE
            for pt, r in self._promo_rects():
                p.rect((240, 236, 224), r, radio=10)
                p.rect((90, 90, 90), r, radio=10, borde=2)
                simbolo = NOMBRES_PROMO[pt] if blanca else NOMBRES_PROMO[pt].lower()
                img = self.img.get(simbolo)
                if img:
                    p.img(img, r.x + (r.w - img.get_width()) // 2,
                          r.y + (r.h - img.get_height()) // 2)


# ============================================================
# MOTOR DE IA
#   1) Si hay un motor UCI ejecutable (Texel / Stockfish) lo usa.
#   2) Si no (o si Android no deja ejecutarlo) usa la IA integrada en Python,
#      que funciona en cualquier celular sin depender de archivos externos.
# ============================================================
MATE = 100000
VALOR = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
         chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


class _Tiempo(Exception):
    pass


class MotorPython:
    """Negamax con poda alfa-beta, profundización iterativa y límite de tiempo."""

    def __init__(self):
        self.limite_t = 0.0
        self.nodos = 0

    @staticmethod
    def evaluar(b):
        total = 0
        piezas = b.piece_map()
        final = len(piezas) <= 10
        for sq, pc in piezas.items():
            t = pc.piece_type
            f, r = chess.square_file(sq), chess.square_rank(sq)
            v = VALOR[t]
            cen = 7 - (abs(f - 3.5) + abs(r - 3.5))          # 0..7 (7 = centro)
            if t == chess.PAWN:
                av = r if pc.color == chess.WHITE else 7 - r
                v += av * 6 + cen * 1.5
            elif t in (chess.KNIGHT, chess.BISHOP):
                v += cen * 4
            elif t == chess.QUEEN:
                v += cen * 1.5
            elif t == chess.ROOK:
                av = r if pc.color == chess.WHITE else 7 - r
                if av == 6:
                    v += 20
            else:                                              # rey
                v += cen * (4 if final else -3)
            total += v if pc.color == chess.WHITE else -v
        return total if b.turn == chess.WHITE else -total

    @staticmethod
    def _orden(b, movs):
        def clave(m):
            s = 0
            if b.is_capture(m):
                vic = b.piece_type_at(m.to_square) or chess.PAWN
                atk = b.piece_type_at(m.from_square) or chess.PAWN
                s += 10 * VALOR[vic] - VALOR[atk] + 1000
            if m.promotion:
                s += 800
            return -s
        movs.sort(key=clave)
        return movs

    def _quies(self, b, alfa, beta, prof):
        self.nodos += 1
        if (self.nodos & 255) == 0 and time.time() > self.limite_t:
            raise _Tiempo()
        pat = self.evaluar(b)
        if pat >= beta:
            return beta
        if pat > alfa:
            alfa = pat
        if prof >= 5:
            return alfa
        for m in self._orden(b, list(b.generate_legal_captures())):
            b.push(m)
            try:
                v = -self._quies(b, -beta, -alfa, prof + 1)
            finally:
                b.pop()
            if v >= beta:
                return beta
            if v > alfa:
                alfa = v
        return alfa

    def _neg(self, b, prof, alfa, beta, ply):
        self.nodos += 1
        if (self.nodos & 255) == 0 and time.time() > self.limite_t:
            raise _Tiempo()
        if b.halfmove_clock >= 100:
            return 0
        movs = list(b.legal_moves)
        if not movs:
            return -MATE + ply if b.is_check() else 0
        if prof <= 0:
            return self._quies(b, alfa, beta, 0)
        for m in self._orden(b, movs):
            b.push(m)
            try:
                v = -self._neg(b, prof - 1, -beta, -alfa, ply + 1)
            finally:
                b.pop()
            if v >= beta:
                return beta
            if v > alfa:
                alfa = v
        return alfa

    def mejor(self, board, prof_max, segundos):
        b = board.copy(stack=False)
        movs = list(b.legal_moves)
        if not movs:
            return None
        self._orden(b, movs)
        mejor = movs[0]
        self.limite_t = time.time() + segundos
        for prof in range(1, prof_max + 1):
            try:
                alfa, cand, cand_v = -MATE - 1, None, None
                for m in movs:
                    b.push(m)
                    try:
                        v = -self._neg(b, prof - 1, -MATE - 1, -alfa, 1)
                    finally:
                        b.pop()
                    if cand is None or v > cand_v:
                        cand, cand_v = m, v
                    if v > alfa:
                        alfa = v
                mejor = cand
                movs.remove(cand)           # la mejor primero en la siguiente profundidad
                movs.insert(0, cand)
                if cand_v > MATE - 100:     # mate encontrado
                    break
            except _Tiempo:
                break
        return mejor


def _perfil_python(elo):
    """(profundidad máxima, segundos) de la IA integrada según el nivel."""
    if elo < 300:
        return 1, 0.5
    if elo < 700:
        return 2, 1.0
    if elo < 1100:
        return 3, 1.5
    if elo < 1650:
        return 3, 2.5
    if elo < 2100:
        return 4, 3.5
    return 5, 4.5


def _dirs_motor(dir_base):
    """Carpetas donde buscar motores: la del programa y la de librerías nativas de Android."""
    carpetas = [dir_base, os.getcwd()]
    try:
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        carpetas.append(str(act.getApplicationInfo().nativeLibraryDir))
    except Exception:
        pass
    return list(dict.fromkeys(c for c in carpetas if c))


class GestorIA:
    def __init__(self, dir_base):
        self.dir_base = dir_base
        self.motor = None
        self.py = MotorPython()
        self.usa_python = False
        self.es_texel = False
        self.etiqueta = ""
        self.limite = None
        self.elo = 500
        self.perr = 0.0
        self.titulo = ""
        self.gen = 0
        self.pensando = False
        self.pendiente = None
        self.estado_carga = None        # None | "cargando" | "ok" | "error"
        self._resultado = None

    # ---------- carga de motor externo (opcional) ----------
    def _candidatos(self, prefijo):
        rutas = []
        for carpeta in _dirs_motor(self.dir_base):
            try:
                nombres = os.listdir(carpeta)
            except OSError:
                continue
            for n in nombres:
                nl = n.lower()
                if nl.endswith((".py", ".pyc", ".png", ".jpg", ".ico", ".json", ".txt", ".atlas")):
                    continue
                if nl.startswith(prefijo) or nl.startswith("lib" + prefijo):
                    rutas.append(os.path.join(carpeta, n))
        return rutas

    def _lanzar(self, ruta):
        try:
            os.chmod(ruta, 0o755)
        except Exception:
            pass
        kw = {"cwd": os.path.dirname(ruta) or None}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000        # sin ventana de consola
        return chess.engine.SimpleEngine.popen_uci(ruta, timeout=8, **kw)

    def _abrir(self, prefijo):
        if not HAY_UCI:
            return None
        for ruta in self._candidatos(prefijo):
            try:
                print(f"[MOTOR] Probando {os.path.basename(ruta)} ...")
                m = self._lanzar(ruta)
                print(f"[MOTOR] OK: {m.id.get('name', os.path.basename(ruta))}")
                return m
            except Exception as e:
                print(f"[MOTOR] No se pudo usar {os.path.basename(ruta)}: {e!r}")
        return None

    @staticmethod
    def _poner(m, deseadas):
        reales = {k.lower(): k for k in m.options.keys()}
        for nombre, valor in deseadas.items():
            real = reales.get(nombre.lower())
            if not real:
                continue
            opt = m.options[real]
            try:
                if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                    if opt.min is not None:
                        valor = max(opt.min, valor)
                    if opt.max is not None:
                        valor = min(opt.max, valor)
                m.configure({real: valor})
            except Exception as e:
                print(f"[MOTOR] No se pudo poner {real}={valor}: {e!r}")

    def _configurar(self, m, es_texel, elo):
        self._poner(m, {"Threads": 1, "Hash": 16})
        reales = {k.lower() for k in m.options.keys()}
        if elo >= ELO_STOCKFISH:
            self._poner(m, {"UCI_LimitStrength": False, "Skill Level": 20})
            return chess.engine.Limit(time=1.5)
        if es_texel:
            if "uci_limitstrength" in reales and "uci_elo" in reales:
                self._poner(m, {"UCI_LimitStrength": True, "UCI_Elo": elo})
            elif "strength" in reales:
                self._poner(m, {"Strength": int(max(0, min(1000, elo / 2540 * 1000)))})
            return chess.engine.Limit(time=0.3 if elo < 500 else 0.8)
        if elo >= 1320 and "uci_elo" in reales:
            self._poner(m, {"UCI_LimitStrength": True, "UCI_Elo": elo})
            return chess.engine.Limit(time=0.5)
        self._poner(m, {"UCI_LimitStrength": False, "Skill Level": max(0, min(20, elo // 110))})
        prof = 1 if elo < 300 else 2 if elo < 600 else 3 if elo < 1000 else 5
        return chess.engine.Limit(depth=prof, time=0.3)

    def cargar(self, idx_nivel):
        elo, titulo, _, perr = NIVELES[idx_nivel]
        self.cerrar()
        self.elo, self.titulo, self.perr = elo, titulo, perr
        self.estado_carga = "cargando"
        self._resultado = None
        gen = self.gen
        threading.Thread(target=self._hilo_carga, args=(elo, gen), daemon=True).start()

    def _hilo_carga(self, elo, gen):
        m, es_texel, etiqueta, limite = None, False, "", None
        try:
            if elo < ELO_STOCKFISH:
                m = self._abrir("texel")
                if m:
                    es_texel, etiqueta = True, "Texel"
                else:
                    m = self._abrir("stockfish")
                    if m:
                        etiqueta = "Stockfish (modo suave)"
            else:
                m = self._abrir("stockfish")
                if m:
                    etiqueta = "Stockfish"
            if m is not None:
                limite = self._configurar(m, es_texel, elo)
        except Exception as e:
            print(f"[MOTOR] Error cargando: {e!r}")
            if m is not None:
                try:
                    m.close()
                except Exception:
                    pass
            m = None
        if m is None:
            etiqueta = "IA integrada"                # siempre hay IA: nunca falla la carga
        if gen != self.gen:                          # cancelado por el usuario
            if m is not None:
                try:
                    m.close()
                except Exception:
                    pass
            return
        self._resultado = (m, es_texel, etiqueta, limite)
        self.estado_carga = "ok"

    def tomar_carga(self):
        """Llamar cuando estado_carga == 'ok' para activar el motor."""
        m, es_texel, etiqueta, limite = self._resultado
        self.motor, self.es_texel, self.etiqueta, self.limite = m, es_texel, etiqueta, limite
        self.usa_python = m is None
        self.estado_carga = None

    # ---------- jugar ----------
    def pensar(self, board):
        self.pensando = True
        self.pendiente = None
        threading.Thread(target=self._hilo_pensar, args=(board.copy(), self.gen), daemon=True).start()

    def _hilo_pensar(self, board, gen):
        mov = None
        legales = list(board.legal_moves)
        try:
            time.sleep(0.3)
            if not legales:
                mov = None
            elif random.random() < self.perr:
                mov = random.choice(legales)          # jugada "distraída" (niños)
            elif self.usa_python or self.motor is None:
                prof, seg = _perfil_python(self.elo)
                mov = self.py.mejor(board, prof, seg)
            else:
                mov = self.motor.play(board, self.limite).move
        except Exception as e:
            print(f"[IA] Error: {e!r}")
            try:                                      # si el motor externo falla, pasa a la IA integrada
                if legales:
                    prof, seg = _perfil_python(self.elo)
                    mov = self.py.mejor(board, min(prof, 3), min(seg, 2.0))
                    self.usa_python = True
            except Exception:
                mov = random.choice(legales) if legales else None
        if mov is not None and mov not in legales:
            mov = random.choice(legales) if legales else None
        if gen == self.gen:
            self.pendiente = mov
            self.pensando = False

    def tomar_jugada(self):
        if not self.pensando and self.pendiente is not None:
            m, self.pendiente = self.pendiente, None
            return m
        return None

    def cancelar(self):
        """Descarta lo que esté pensando la IA."""
        self.gen += 1
        self.pensando = False
        self.pendiente = None

    def cerrar(self, sincrono=False):
        self.cancelar()
        self.estado_carga = None
        m, self.motor = self.motor, None
        if m is None:
            return

        def _cerrar():
            try:
                m.quit()
            except Exception:
                try:
                    m.close()
                except Exception:
                    pass
        if sincrono:
            _cerrar()
        else:
            threading.Thread(target=_cerrar, daemon=True).start()


# ============================================================
# AJEDREZ 4 JUGADORES
# ============================================================
# Tablero de 14x14 con las 4 esquinas de 3x3 recortadas (formato estándar).
# Cada jugador tiene 16 piezas en su lado: sus 8 piezas + 8 peones; el tablero
# se extiende 3 casillas a cada lado de ellos.
# Reglas: orden Rojo -> Azul -> Amarillo -> Verde. No hay "jaque": gana el
# último jugador con rey; quien pierde su rey queda eliminado (sus piezas
# quedan grises y se pueden capturar). Sin enroque ni al paso.
N4 = 14
NOM_ASIENTO = ["Rojo", "Azul", "Amarillo", "Verde"]
COL_ASIENTO = [(214, 66, 66), (66, 120, 222), (232, 190, 44), (72, 172, 88)]
DIR_PEON = [(-1, 0), (0, 1), (1, 0), (0, -1)]
BASE = "RNBQKBNR"
PROMO_LINEA = [("r", 3), ("c", 10), ("r", 10), ("c", 3)]
INICIO_PEON = [("r", 12), ("c", 1), ("r", 1), ("c", 12)]


def valido(r, c):
    return 0 <= r < N4 and 0 <= c < N4 and not ((r < 3 or r > 10) and (c < 3 or c > 10))


def rot_cw(r, c):
    return c, N4 - 1 - r


class Ajedrez4:
    clave = "ajedrez4"
    titulo = "Ajedrez 4 jugadores"

    def __init__(self, ctx):
        self.ctx = ctx
        self.T = ctx.rect.w // N4
        self.ox = ctx.rect.x + (ctx.rect.w - N4 * self.T) // 2
        self.oy = ctx.rect.y + (ctx.rect.h - N4 * self.T) // 2
        base = {}
        for s, a in ARCHIVOS_PIEZAS.items():
            if s.isupper():
                base[s] = ctx.cargar_fit(a, self.T, self.T)
        self.img = {}
        for seat, color in enumerate(COL_ASIENTO + [(128, 128, 128)]):
            for t, im in base.items():
                if im:
                    self.img[(seat if seat < 4 else -1, t)] = im.tintada(color)
        self.interactivo = False
        self.nueva([0, 1, 2, 3])

    # ---------- estado ----------
    def nueva(self, activos, mi_asiento=0, rotar=True):
        self.activos = list(activos)
        self.mi_asiento = mi_asiento
        self.rotar = rotar
        self.p = {}
        for s in self.activos:
            for i, t in enumerate(BASE):
                r, c = 13, 3 + i
                pr, pc = 12, 3 + i
                for _ in range(s):
                    r, c = rot_cw(r, c)
                    pr, pc = rot_cw(pr, pc)
                self.p[(r, c)] = (s, t)
                self.p[(pr, pc)] = (s, "P")
        self.vivos = set(self.activos)
        self.turno_asiento = min(self.activos)
        self.sel = None
        self.destinos = []
        self.promo = None
        self.ultimo = None
        self.fin = None
        self.n_jugadas = 0

    # ---------- reglas ----------
    def _linea_promo(self, s, r, c):
        eje, v = PROMO_LINEA[s]
        return (r if eje == "r" else c) == v

    def _destinos(self, r, c):
        s, t = self.p[(r, c)]
        res = []

        def estado(rr, cc):
            if not valido(rr, cc):
                return None
            o = self.p.get((rr, cc))
            if o is None:
                return "libre"
            return "enemigo" if o[0] != s else None

        if t == "P":
            dr, dc = DIR_PEON[s]
            r1, c1 = r + dr, c + dc
            if estado(r1, c1) == "libre":
                res.append((r1, c1))
                eje, v = INICIO_PEON[s]
                if (r if eje == "r" else c) == v:
                    r2, c2 = r + 2 * dr, c + 2 * dc
                    if estado(r2, c2) == "libre":
                        res.append((r2, c2))
            for pr, pc in ((dc, dr), (-dc, -dr)):
                rr, cc = r + dr + pr, c + dc + pc
                if estado(rr, cc) == "enemigo":
                    res.append((rr, cc))
        elif t == "N":
            for dr, dc in ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)):
                if estado(r + dr, c + dc) in ("libre", "enemigo"):
                    res.append((r + dr, c + dc))
        elif t == "K":
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr or dc) and estado(r + dr, c + dc) in ("libre", "enemigo"):
                        res.append((r + dr, c + dc))
        else:
            ortog = ((1, 0), (-1, 0), (0, 1), (0, -1))
            diag = ((1, 1), (1, -1), (-1, 1), (-1, -1))
            dirs = ortog if t == "R" else diag if t == "B" else ortog + diag
            for dr, dc in dirs:
                rr, cc = r + dr, c + dc
                while True:
                    e = estado(rr, cc)
                    if e is None:
                        break
                    res.append((rr, cc))
                    if e == "enemigo":
                        break
                    rr += dr
                    cc += dc
        return res

    def _tiene_mov(self, s):
        return any(v[0] == s and self._destinos(*k) for k, v in self.p.items())

    def _siguiente(self):
        if len(self.vivos) <= 1:
            ganador = next(iter(self.vivos)) if self.vivos else None
            self.fin = ("gana", ganador, "Último jugador en pie")
            return
        cur = self.turno_asiento
        for k in range(1, 5):
            s = (cur + k) % 4
            if s in self.vivos and self._tiene_mov(s):
                self.turno_asiento = s
                return
        self.fin = ("tablas", None, "Nadie puede mover")

    def eliminar(self, seat):
        """Un jugador sale de la partida (rey capturado o desconexión)."""
        if seat not in self.vivos:
            return
        self.vivos.discard(seat)
        if self.fin:
            return
        if len(self.vivos) <= 1 or self.turno_asiento == seat:
            self._siguiente()

    def en_peligro(self, seat):
        rey = next((k for k, v in self.p.items() if v == (seat, "K")), None)
        if rey is None:
            return False
        for k, v in self.p.items():
            if v[0] != seat and v[0] in self.vivos and rey in self._destinos(*k):
                return True
        return False

    def _ejecutar(self, fr, fc, tr, tc, promo):
        s, t = self.p.pop((fr, fc))
        cap = self.p.get((tr, tc))
        if t == "P" and self._linea_promo(s, tr, tc):
            t = promo if promo in ("Q", "R", "B", "N") else "Q"
        self.p[(tr, tc)] = (s, t)
        self.ultimo = ((fr, fc), (tr, tc))
        self.n_jugadas += 1
        if cap and cap[1] == "K":
            self.vivos.discard(cap[0])
        self.sel, self.destinos, self.promo = None, [], None
        self._siguiente()

    def validar(self, seat, dato):
        try:
            fr, fc, tr, tc = [int(x) for x in dato[:4]]
        except Exception:
            return False
        v = self.p.get((fr, fc))
        return bool(not self.fin and seat == self.turno_asiento and v and v[0] == seat
                    and (tr, tc) in self._destinos(fr, fc))

    # ---------- API ----------
    def aplicar(self, dato):
        if self.validar(self.turno_asiento, dato):
            promo = dato[4] if len(dato) > 4 else ""
            self._ejecutar(int(dato[0]), int(dato[1]), int(dato[2]), int(dato[3]), promo)

    def resultado(self):
        return self.fin

    def clic(self, pos):
        if self.fin:
            return None
        if self.promo:
            elegido = self._promo_en(pos)
            (fr, fc), (tr, tc) = self.promo
            self.promo = None
            if elegido:
                self._ejecutar(fr, fc, tr, tc, elegido)
                return [fr, fc, tr, tc, elegido]
            self.sel, self.destinos = None, []
            return None
        rc = self._a_logica_px(pos)
        if rc is None:
            return None
        r, c = rc
        if self.sel and (r, c) in self.destinos:
            fr, fc = self.sel
            s, t = self.p[(fr, fc)]
            if t == "P" and self._linea_promo(s, r, c):
                self.promo = ((fr, fc), (r, c))
                return None
            self._ejecutar(fr, fc, r, c, "")
            return [fr, fc, r, c, ""]
        v = self.p.get((r, c))
        if v and v[0] == self.turno_asiento:
            self.sel = (r, c)
            self.destinos = self._destinos(r, c)
        else:
            self.sel, self.destinos = None, []
        return None

    # ---------- vista (rotación) ----------
    def _rot(self):
        return self.turno_asiento if self.rotar else self.mi_asiento

    def _a_pantalla(self, r, c):
        k = self._rot()
        if k == 0:
            return r, c
        if k == 1:
            return N4 - 1 - c, r
        if k == 2:
            return N4 - 1 - r, N4 - 1 - c
        return c, N4 - 1 - r

    def _a_logica(self, dr, dc):
        k = self._rot()
        if k == 0:
            return dr, dc
        if k == 1:
            return dc, N4 - 1 - dr
        if k == 2:
            return N4 - 1 - dr, N4 - 1 - dc
        return N4 - 1 - dc, dr

    def _a_logica_px(self, pos):
        x, y = pos[0] - self.ox, pos[1] - self.oy
        if x < 0 or y < 0:
            return None
        dc, dr = int(x // self.T), int(y // self.T)
        if not (0 <= dr < N4 and 0 <= dc < N4):
            return None
        r, c = self._a_logica(dr, dc)
        return (r, c) if valido(r, c) else None

    def _xy(self, r, c):
        dr, dc = self._a_pantalla(r, c)
        return self.ox + dc * self.T, self.oy + dr * self.T

    def _promo_rects(self):
        w = int(self.T * 1.5)
        x0 = self.ox + (N4 * self.T - 4 * w) // 2
        y0 = self.oy + (N4 * self.T - w) // 2
        return [(t, Rect(x0 + i * w, y0, w, w)) for i, t in enumerate("QRBN")]

    def _promo_en(self, pos):
        for t, r in self._promo_rects():
            if r.collidepoint(pos):
                return t
        return None

    # ---------- dibujo ----------
    def dibujar(self, p):
        T = self.T
        col = self.ctx.colores_tablero
        for r in range(N4):
            for c in range(N4):
                if valido(r, c):
                    x, y = self._xy(r, c)
                    p.rect(col[(r + c) % 2], (x, y, T, T))
        if self.ultimo:
            for rc in self.ultimo:
                x, y = self._xy(*rc)
                p.rect((255, 226, 70, 110), (x, y, T, T))
        if self.sel:
            x, y = self._xy(*self.sel)
            p.rect((90, 200, 90, 140), (x, y, T, T))

        # rey en peligro del jugador al que le toca
        if not self.fin and self.turno_asiento in self.vivos and self.en_peligro(self.turno_asiento):
            rey = next((k for k, v in self.p.items() if v == (self.turno_asiento, "K")), None)
            if rey:
                x, y = self._xy(*rey)
                p.circulo((220, 40, 40, 180), (x + T // 2, y + T // 2), T // 2)

        for (r, c), (s, t) in self.p.items():
            x, y = self._xy(r, c)
            img = self.img.get((s if s in self.vivos else -1, t))
            if img:
                p.img(img, x + (T - img.get_width()) // 2, y + (T - img.get_height()) // 2)
            else:
                colr = COL_ASIENTO[s] if s in self.vivos else (128, 128, 128)
                p.circulo(colr, (x + T // 2, y + T // 2), T // 2 - 3)
                p.texto(t, x + T // 2, y + T // 2 - 9, self.ctx.F["chica"], (0, 0, 0), centro=True)

        for (r, c) in self.destinos:
            x, y = self._xy(r, c)
            if (r, c) in self.p:
                p.circulo((40, 130, 40, 200), (x + T // 2, y + T // 2), T // 2 - 5, borde=4)
            else:
                p.circulo((40, 130, 40, 190), (x + T // 2, y + T // 2), 8)

        # marco del color del jugador que mueve
        marco = (self.ox - 4, self.oy - 4, N4 * T + 8, N4 * T + 8)
        if self.turno_asiento in self.vivos or not self.fin:
            p.rect(COL_ASIENTO[self.turno_asiento], marco, radio=6, borde=4)

        if self.promo:
            p.rect((0, 0, 0, 150), (self.ox, self.oy, N4 * T, N4 * T))
            for t, r in self._promo_rects():
                p.rect((240, 236, 224), r, radio=10)
                p.rect((90, 90, 90), r, radio=10, borde=2)
                img = self.img.get((self.turno_asiento, t))
                if img:
                    p.img(img, r.x + (r.w - img.get_width()) // 2,
                          r.y + (r.h - img.get_height()) // 2)
                else:
                    p.texto(t, r.centerx, r.centery - 10, self.ctx.F["h3"], (0, 0, 0), centro=True)
