"""Gera um ícone quadrado full-bleed a partir da arte neon (uso pontual)."""

from PIL import Image, ImageChops, ImageFilter

SIZE = 1024
SRC = "app_icon_v2.png"
OUT = "app_icon.png"


def _smoothstep(mask: Image.Image, lo: int, hi: int) -> Image.Image:
    """Mapeia luminância [lo, hi] -> [0, 255], suavizando bordas."""
    lut = []
    for v in range(256):
        if v <= lo:
            t = 0.0
        elif v >= hi:
            t = 1.0
        else:
            x = (v - lo) / (hi - lo)
            t = x * x * (3 - 2 * x)
        lut.append(int(t * 255))
    return mask.point(lut)


def main() -> None:
    art = Image.open(SRC).convert("RGB")
    nova_alt = round(art.height * SIZE / art.width)
    art = art.resize((SIZE, nova_alt), Image.LANCZOS)

    base_art = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    base_art.paste(art, (0, (SIZE - nova_alt) // 2))

    r, _g, b = base_art.split()
    azul = ImageChops.subtract(b, r)
    alpha = _smoothstep(azul, 45, 110)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))

    final = base_art.convert("RGBA")
    final.putalpha(alpha)
    final.save(OUT)
    print(f"OK -> {OUT} ({final.size[0]}x{final.size[1]}, transparente)")


if __name__ == "__main__":
    main()
