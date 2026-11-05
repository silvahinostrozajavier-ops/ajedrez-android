# juego_tresenraya.py — 3 en raya (usa tablero_3_en_raya.png, equis_3_en_raya.png,
#                       circulo_3_en_raya.png)
from gfx import Rect

# ---- AJUSTES DE IMAGEN (cámbialos si las fichas no caen centradas) ----
# Márgenes vacíos que tiene la imagen del tablero alrededor de la cuadrícula,
# como fracción del tamaño de la imagen: (izquierda, arriba, derecha, abajo)
MARGEN_TABLERO = (0.08, 0.06, 0.08, 0.08)
ESCALA_FICHA = 0.70      # tamaño de la X / O respecto a una casilla

LINEAS = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8),
          (0, 4, 8), (2, 4, 6)]


class TresEnRaya:
    clave = "tresenraya"
    titulo = "3 en raya"
    lados = ("X", "O")

    def __init__(self, ctx):
        self.ctx = ctx
        r = ctx.rect
        raw = ctx.cargar("tablero_3_en_raya.png")
        if raw:
            w0, h0 = raw.get_size()
            esc = min(r.w / w0, r.h / h0)
            w, h = int(w0 * esc), int(h0 * esc)
            self.img_tab = ctx.cargar_fit("tablero_3_en_raya.png", w, h)
        else:
            self.img_tab = None
            w, h = r.w, int(r.w * 0.88)
        self.area = Rect(0, 0, w, h)
        self.area.center = r.center
        ml, mt, mr, mb = MARGEN_TABLERO
        self.grid = Rect(self.area.x + int(w * ml), self.area.y + int(h * mt),
                                int(w * (1 - ml - mr)), int(h * (1 - mt - mb)))
        self.cw = self.grid.w / 3
        self.ch = self.grid.h / 3
        lado = int(min(self.cw, self.ch) * ESCALA_FICHA)
        self.img = [ctx.cargar_fit("equis_3_en_raya.png", lado, lado),
                    ctx.cargar_fit("circulo_3_en_raya.png", lado, lado)]
        self.interactivo = False
        self.nueva()

    # ---------- estado ----------
    def nueva(self, mi_lado=0, orientar=False):
        self.mi_lado = mi_lado
        self.cas = [None] * 9
        self.turno = 0
        self.hist = []
        self.linea = None
        self._res = None

    def _centro(self, idx):
        f, c = divmod(idx, 3)
        return (int(round(self.grid.x + (c + 0.5) * self.cw)),
                int(round(self.grid.y + (f + 0.5) * self.ch)))

    def _celda(self, pos):
        if not self.grid.collidepoint(pos):
            return None
        c = int((pos[0] - self.grid.x) / self.cw)
        f = int((pos[1] - self.grid.y) / self.ch)
        if c < 0 or c > 2 or f < 0 or f > 2:
            return None
        return f * 3 + c

    def _poner(self, idx):
        self.cas[idx] = self.turno
        self.hist.append((self.turno, idx))
        self.turno = 1 - self.turno
        for a, b, c in LINEAS:
            if self.cas[a] is not None and self.cas[a] == self.cas[b] == self.cas[c]:
                self._res = ("gana", self.cas[a], "3 en raya")
                self.linea = (a, c)
                return
        if all(v is not None for v in self.cas):
            self._res = ("tablas", None, "Empate")

    # ---------- API común ----------
    def clic(self, pos):
        if self._res:
            return None
        idx = self._celda(pos)
        if idx is None or self.cas[idx] is not None:
            return None
        self._poner(idx)
        return idx

    def aplicar(self, dato):
        try:
            idx = int(dato)
        except Exception:
            return
        if not self._res and 0 <= idx < 9 and self.cas[idx] is None:
            self._poner(idx)

    def resultado(self):
        return self._res

    def jugadas(self):
        filas = []
        for i in range(0, len(self.hist), 2):
            def t(h):
                lado, idx = h
                return f"{'XO'[lado]} ({idx // 3 + 1},{idx % 3 + 1})"
            a = t(self.hist[i])
            b = t(self.hist[i + 1]) if i + 1 < len(self.hist) else ""
            filas.append((i // 2 + 1, a, b))
        return filas

    # ---------- dibujo ----------
    def dibujar(self, p):
        if self.img_tab:
            p.img(self.img_tab, self.area.x, self.area.y)
        else:
            p.rect((240, 240, 240), self.area, radio=12)
            for i in (1, 2):
                x = int(self.grid.x + i * self.cw)
                y = int(self.grid.y + i * self.ch)
                p.linea((60, 60, 60), (x, self.grid.y), (x, self.grid.bottom), 6)
                p.linea((60, 60, 60), (self.grid.x, y), (self.grid.right, y), 6)
        for idx, v in enumerate(self.cas):
            if v is None:
                continue
            cx, cy = self._centro(idx)
            img = self.img[v]
            if img:
                p.img(img, cx - img.get_width() // 2, cy - img.get_height() // 2)
            else:
                rad = int(min(self.cw, self.ch) * 0.28)
                if v == 0:
                    p.linea((200, 60, 60), (cx - rad, cy - rad), (cx + rad, cy + rad), 10)
                    p.linea((200, 60, 60), (cx + rad, cy - rad), (cx - rad, cy + rad), 10)
                else:
                    p.circulo((60, 100, 200), (cx, cy), rad, borde=10)
        if self.linea:
            p.linea((255, 214, 102), self._centro(self.linea[0]),
                    self._centro(self.linea[1]), 10)
