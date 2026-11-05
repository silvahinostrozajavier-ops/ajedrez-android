# Convierte icono.ico -> icono.png (Android necesita PNG). Si falla, usa una ficha como icono.
import os
import shutil
from PIL import Image

try:
    im = Image.open("icono.ico")
    tam = max(im.info.get("sizes", {im.size}))
    im.size = tam
    im.load()
    im.convert("RGBA").resize((512, 512), Image.LANCZOS).save("icono.png")
    print("icono.png creado desde icono.ico")
except Exception as e:
    print("No se pudo leer icono.ico:", e)
    for alt in ("peon_blanco.png", "w_Caballo.png"):
        if os.path.exists(alt):
            shutil.copy(alt, "icono.png")
            print("Usando", alt, "como icono")
            break
    else:
        Image.new("RGBA", (512, 512), (38, 44, 60, 255)).save("icono.png")
