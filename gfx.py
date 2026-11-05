# gfx.py — capa de dibujo sobre Kivy (reemplaza a pygame.draw).
# Se dibuja en un "lienzo virtual" de W x H con el origen ARRIBA-IZQUIERDA
# (igual que en la versión de PC); aquí se convierte a las coordenadas de Kivy.
import os

try:
    from kivy.graphics import Color, Rectangle, RoundedRectangle, Line, Ellipse
    from kivy.core.text import Label as CoreLabel
    from kivy.core.image import Image as CoreImage
except Exception:                      # permite probar la lógica sin Kivy
    Color = Rectangle = RoundedRectangle = Line = Ellipse = None
    CoreLabel = CoreImage = None


class Rect:
    """Rectángulo mínimo con la misma interfaz que usaba pygame.Rect."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def __iter__(self):
        return iter((self.x, self.y, self.w, self.h))

    def __getitem__(self, i):
        return (self.x, self.y, self.w, self.h)[i]

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def centerx(self):
        return self.x + self.w // 2

    @property
    def centery(self):
        return self.y + self.h // 2

    @property
    def center(self):
        return (self.centerx, self.centery)

    @center.setter
    def center(self, c):
        self.x = int(c[0] - self.w // 2)
        self.y = int(c[1] - self.h // 2)

    @property
    def topleft(self):
        return (self.x, self.y)

    @property
    def size(self):
        return (self.w, self.h)

    def collidepoint(self, pos):
        return self.x <= pos[0] < self.x + self.w and self.y <= pos[1] < self.y + self.h

    def move(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


class Img:
    """Textura + tamaño (en unidades virtuales) + tinte opcional."""

    def __init__(self, tex, w, h, tint=None):
        self.tex, self.w, self.h, self.tint = tex, w, h, tint

    def get_width(self):
        return self.w

    def get_height(self):
        return self.h

    def get_size(self):
        return (self.w, self.h)

    def tintada(self, color):
        return Img(self.tex, self.w, self.h, color)


class Recursos:
    """Carga de imágenes con caché y manejo de errores (nunca lanza)."""

    def __init__(self, carpetas):
        self.carpetas = carpetas
        self.cache = {}

    def buscar(self, nombre):
        for c in self.carpetas:
            ruta = os.path.join(c, nombre)
            if os.path.exists(ruta):
                return ruta
        return None

    def cargar(self, nombre):
        if nombre in self.cache:
            return self.cache[nombre]
        img = None
        ruta = self.buscar(nombre)
        if ruta and CoreImage is not None:
            try:
                tex = CoreImage(ruta).texture
                tex.mag_filter = "linear"
                tex.min_filter = "linear"
                img = Img(tex, tex.width, tex.height)
            except Exception as e:
                print("AVISO: no se pudo cargar", nombre, e)
        else:
            print("AVISO: no se encontró", nombre)
        self.cache[nombre] = img
        return img

    def cargar_fit(self, nombre, max_w, max_h):
        img = self.cargar(nombre)
        if img is None:
            return None
        esc = min(max_w / img.w, max_h / img.h)
        return Img(img.tex, max(1, int(img.w * esc)), max(1, int(img.h * esc)))


class Gfx:
    """Contexto de dibujo. Todas las coordenadas son virtuales (y hacia abajo)."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.esc = 1.0                  # escala virtual -> píxeles (para nitidez del texto)
        self._tx = {}

    # ---------- color ----------
    @staticmethod
    def _col(c):
        if len(c) == 4:
            Color(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, c[3] / 255.0)
        else:
            Color(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1)

    # ---------- primitivas ----------
    def rect(self, color, r, radio=0, borde=0):
        x, y, w, h = r[0], r[1], r[2], r[3]
        ky = self.H - y - h
        self._col(color)
        radio = max(0, min(radio, min(w, h) // 2))
        if borde:
            if radio:
                Line(rounded_rectangle=(x, ky, w, h, radio), width=borde)
            else:
                Line(rectangle=(x, ky, w, h), width=borde)
        elif radio:
            RoundedRectangle(pos=(x, ky), size=(w, h), radius=[radio])
        else:
            Rectangle(pos=(x, ky), size=(w, h))

    def circulo(self, color, centro, radio, borde=0):
        cx, cy = centro
        ky = self.H - cy
        self._col(color)
        if borde:
            Line(circle=(cx, ky, radio), width=borde)
        else:
            Ellipse(pos=(cx - radio, ky - radio), size=(2 * radio, 2 * radio))

    def linea(self, color, a, b, grosor=2):
        self._col(color)
        Line(points=[a[0], self.H - a[1], b[0], self.H - b[1]], width=grosor)

    def img(self, im, x, y, w=None, h=None):
        if im is None:
            return
        w = im.w if w is None else w
        h = im.h if h is None else h
        Color(*(((im.tint[0] / 255.0, im.tint[1] / 255.0, im.tint[2] / 255.0, 1))
                if im.tint else (1, 1, 1, 1)))
        Rectangle(texture=im.tex, pos=(x, self.H - y - h), size=(w, h))

    def fondo_degradado(self, tex):
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(0, 0), size=(self.W, self.H))

    # ---------- texto ----------
    def _textura(self, s, fuente):
        tam, negrita = fuente
        key = (s, tam, negrita, int(self.esc * 10))
        t = self._tx.get(key)
        if t is None:
            if len(self._tx) > 700:
                self._tx.clear()
            try:
                lab = CoreLabel(text=s, font_size=max(6, int(round(tam * self.esc))),
                                bold=negrita)
                lab.refresh()
                t = lab.texture
            except Exception:
                t = None
            self._tx[key] = t
        return t

    def medir(self, s, fuente):
        if not s:
            return (0, 0)
        t = self._textura(s, fuente)
        if t is None:
            return (len(s) * fuente[0] * 0.5, fuente[0])
        return (t.width / self.esc, t.height / self.esc)

    def recortar(self, s, fuente, max_w):
        if self.medir(s, fuente)[0] <= max_w:
            return s
        while len(s) > 1 and self.medir(s + "…", fuente)[0] > max_w:
            s = s[:-1]
        return s + "…"

    def texto(self, s, x, y, fuente, color=(255, 255, 255), centro=False, derecha=False,
              max_w=None):
        s = str(s)
        if max_w:
            s = self.recortar(s, fuente, max_w)
        w, h = self.medir(s, fuente)
        if centro:
            x -= w / 2.0
        elif derecha:
            x -= w
        t = self._textura(s, fuente) if s else None
        if t is not None:
            self._col(color)
            Rectangle(texture=t, pos=(x, self.H - y - h), size=(w, h))
        return Rect(int(x), int(y), int(w), int(h))
