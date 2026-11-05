# juego_damas.py — Damas (8x8, captura obligatoria, la ficha corona como DAMA)
#
# Reglas: las fichas avanzan en diagonal; pueden capturar hacia delante y hacia
# atrás; la captura es obligatoria y se encadena; al llegar al fondo la ficha
# se corona como dama (se mueve y captura a cualquier distancia en diagonal).
#
# Imágenes: peon_blanco.png, peon_negro.png, peon_blanco_dama.png (o
#           peon_dama_blanca.png), peon_negro_dama.png
# (el dibujo usa gfx.py / Kivy)

DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def dentro(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def nombre_casilla(r, c):
    return "abcdefgh"[c] + str(8 - r)


class Damas:
    clave = "damas"
    titulo = "Damas"
    lados = ("Blancas", "Negras")

    def __init__(self, ctx):
        self.ctx = ctx
        rect = ctx.rect
        self.T = rect.w // 8
        self.ox = rect.x + (rect.w - 8 * self.T) // 2
        self.oy = rect.y + (rect.h - 8 * self.T) // 2
        s = int(self.T * 0.9)
        self.img = {
            1: ctx.cargar_fit("peon_blanco.png", s, s),
            -1: ctx.cargar_fit("peon_negro.png", s, s),
            2: ctx.cargar_fit("peon_blanco_dama.png", s, s)
               or ctx.cargar_fit("peon_dama_blanca.png", s, s),
            -2: ctx.cargar_fit("peon_negro_dama.png", s, s),
        }
        self.interactivo = False
        self.nueva()

    # ---------- estado ----------
    def nueva(self, mi_lado=0, orientar=False):
        self.mi_lado = mi_lado
        self.volteo = bool(orientar and mi_lado == 1)
        self.t = [[0] * 8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                if (r + c) % 2 == 1:
                    if r < 3:
                        self.t[r][c] = -1
                    elif r > 4:
                        self.t[r][c] = 1
        self.turno = 0
        self.forzada = None
        self.sel = None
        self.destinos = []
        self.turnos = []          # [[lado, "c3-d4"], ...]
        self.ultimo = None
        self.sin_progreso = 0
        self._res = None

    # ---------- reglas ----------
    def _capturas(self, r, c):
        v = self.t[r][c]
        res = []
        if abs(v) == 1:
            for dr, dc in DIRS:
                r1, c1, r2, c2 = r + dr, c + dc, r + 2 * dr, c + 2 * dc
                if dentro(r2, c2) and self.t[r1][c1] != 0 \
                        and (self.t[r1][c1] > 0) != (v > 0) and self.t[r2][c2] == 0:
                    res.append((r, c, r2, c2, (r1, c1)))
        else:
            for dr, dc in DIRS:
                rr, cc = r + dr, c + dc
                while dentro(rr, cc) and self.t[rr][cc] == 0:
                    rr += dr
                    cc += dc
                if dentro(rr, cc) and (self.t[rr][cc] > 0) != (v > 0):
                    cap = (rr, cc)
                    r2, c2 = rr + dr, cc + dc
                    while dentro(r2, c2) and self.t[r2][c2] == 0:
                        res.append((r, c, r2, c2, cap))
                        r2 += dr
                        c2 += dc
        return res

    def _simples(self, r, c):
        v = self.t[r][c]
        res = []
        if abs(v) == 1:
            fwd = -1 if v > 0 else 1
            for dc in (-1, 1):
                r1, c1 = r + fwd, c + dc
                if dentro(r1, c1) and self.t[r1][c1] == 0:
                    res.append((r, c, r1, c1, None))
        else:
            for dr, dc in DIRS:
                rr, cc = r + dr, c + dc
                while dentro(rr, cc) and self.t[rr][cc] == 0:
                    res.append((r, c, rr, cc, None))
                    rr += dr
                    cc += dc
        return res

    def _jugadas_lado(self, lado):
        if self.forzada:
            return self._capturas(*self.forzada)
        signo = 1 if lado == 0 else -1
        caps, simples = [], []
        for r in range(8):
            for c in range(8):
                if self.t[r][c] * signo > 0:
                    caps += self._capturas(r, c)
        if caps:
            return caps
        for r in range(8):
            for c in range(8):
                if self.t[r][c] * signo > 0:
                    simples += self._simples(r, c)
        return simples

    def _paso(self, m):
        r, c, r2, c2, cap = m
        v = self.t[r][c]
        lado = 0 if v > 0 else 1
        self.t[r][c] = 0
        if cap:
            self.t[cap[0]][cap[1]] = 0
        coronada = False
        if v == 1 and r2 == 0:
            v, coronada = 2, True
        elif v == -1 and r2 == 7:
            v, coronada = -2, True
        self.t[r2][c2] = v
        self.ultimo = ((r, c), (r2, c2))

        if self.forzada and self.turnos and self.turnos[-1][0] == lado:
            self.turnos[-1][1] += "x" + nombre_casilla(r2, c2)
        else:
            self.turnos.append([lado, nombre_casilla(r, c) + ("x" if cap else "-")
                                + nombre_casilla(r2, c2)])

        if cap and self._capturas(r2, c2):
            self.forzada = (r2, c2)          # debe seguir capturando
        else:
            self.forzada = None
            self.turno = 1 - lado

        if cap or abs(v) == 1 or coronada:
            self.sin_progreso = 0
        else:
            self.sin_progreso += 1
        self._revisar()

    def _revisar(self):
        if self.forzada:
            return
        if not self._jugadas_lado(self.turno):
            self._res = ("gana", 1 - self.turno, "Sin jugadas para el rival")
        elif self.sin_progreso >= 40:
            self._res = ("tablas", None, "Tablas por falta de progreso")

    # ---------- coordenadas ----------
    def _px(self, r, c):
        if self.volteo:
            r, c = 7 - r, 7 - c
        return self.ox + c * self.T, self.oy + r * self.T

    def _rc(self, pos):
        x, y = pos[0] - self.ox, pos[1] - self.oy
        if x < 0 or y < 0:
            return None
        c, r = int(x // self.T), int(y // self.T)
        if not (0 <= r < 8 and 0 <= c < 8):
            return None
        if self.volteo:
            r, c = 7 - r, 7 - c
        return int(r), int(c)

    # ---------- API común ----------
    def clic(self, pos):
        rc = self._rc(pos)
        if rc is None or self._res:
            return None
        r, c = rc
        if self.sel:
            for m in self.destinos:
                if (m[2], m[3]) == (r, c):
                    self._paso(m)
                    self.sel = self.forzada
                    self.destinos = self._capturas(*self.forzada) if self.forzada else []
                    return [m[0], m[1], m[2], m[3]]
        signo = 1 if self.turno == 0 else -1
        if not self.forzada and self.t[r][c] * signo > 0:
            ds = [m for m in self._jugadas_lado(self.turno) if (m[0], m[1]) == (r, c)]
            if ds:
                self.sel, self.destinos = (r, c), ds
                return None
        if not self.forzada:
            self.sel, self.destinos = None, []
        return None

    def aplicar(self, dato):
        try:
            r, c, r2, c2 = [int(x) for x in dato]
        except Exception:
            return
        if self._res:
            return
        for m in self._jugadas_lado(self.turno):
            if (m[0], m[1], m[2], m[3]) == (r, c, r2, c2):
                self._paso(m)
                self.sel, self.destinos = None, []
                return

    def resultado(self):
        return self._res

    def jugadas(self):
        filas = []
        for i in range(0, len(self.turnos), 2):
            a = self.turnos[i][1]
            b = self.turnos[i + 1][1] if i + 1 < len(self.turnos) else ""
            filas.append((i // 2 + 1, a, b))
        return filas

    # ---------- dibujo ----------
    def dibujar(self, p):
        T = self.T
        col = self.ctx.colores_tablero
        F = self.ctx.F["coord"]
        for r in range(8):
            for c in range(8):
                x, y = self._px(r, c)
                oscura = (r + c) % 2 == 1
                p.rect(col[1] if oscura else col[0], (x, y, T, T))
                if c == (7 if self.volteo else 0):
                    p.texto(str(8 - r), x + 3, y + 2, F, col[0] if oscura else col[1])
                if r == (0 if self.volteo else 7):
                    p.texto("abcdefgh"[c], x + T - 11, y + T - 16, F,
                            col[0] if oscura else col[1])

        if self.ultimo:
            for rc in self.ultimo:
                x, y = self._px(*rc)
                p.rect((255, 226, 70, 100), (x, y, T, T))

        # fichas que pueden mover (útil cuando la captura es obligatoria)
        if self.interactivo and not self.sel and not self._res:
            for m in {(m[0], m[1]) for m in self._jugadas_lado(self.turno)}:
                x, y = self._px(*m)
                p.rect((255, 150, 40, 90), (x, y, T, T))
        if self.sel:
            x, y = self._px(*self.sel)
            p.rect((90, 200, 90, 140), (x, y, T, T))

        for r in range(8):
            for c in range(8):
                v = self.t[r][c]
                if not v:
                    continue
                x, y = self._px(r, c)
                img = self.img.get(v)
                if img:
                    p.img(img, x + (T - img.get_width()) // 2, y + (T - img.get_height()) // 2)
                else:
                    cc = (245, 245, 245) if v > 0 else (30, 30, 34)
                    p.circulo((120, 120, 120), (x + T // 2, y + T // 2), int(T * 0.4))
                    p.circulo(cc, (x + T // 2, y + T // 2), int(T * 0.36))
                    if abs(v) == 2:
                        p.circulo((230, 190, 50), (x + T // 2, y + T // 2), int(T * 0.16))

        for m in self.destinos:
            x, y = self._px(m[2], m[3])
            if m[4]:
                p.circulo((40, 130, 40, 200), (x + T // 2, y + T // 2), T // 2 - 6, borde=5)
            else:
                p.circulo((40, 130, 40, 190), (x + T // 2, y + T // 2), 12)

        p.rect(self.ctx.C_BORDE, (self.ox - 1, self.oy - 1, 8 * T + 2, 8 * T + 2), borde=2)
