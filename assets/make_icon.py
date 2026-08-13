"""로고 PNG → assets/app.ico (다중 크기).

아이콘은 '로고 전체'가 아니라 **심볼(나무+화살표)** 을 쓴다.
16px에서 "Well Root 웰루트 발주 도우미"는 어차피 뭉개진 얼룩이 된다.
"""

from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent / "logo_source.png"  # 원본 로고 PNG를 이 이름으로 두면 된다
OUT = Path(__file__).parent
DEST = OUT / "app.ico"

# 원본(2048²)에서 나무 심볼만. 좌우 글자 조각이 안 들어오게 좁게 잡았다.
SYMBOL_BOX = (655, 80, 1335, 940)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def cut_background(im: Image.Image) -> Image.Image:
    """흰 배경을 투명하게. 로고는 채도가 있고 배경은 거의 무채색이라 채도로 가른다.

    밝기로 자르면 로고의 밝은 하이라이트까지 날아간다.
    """
    im = im.convert("RGB")
    px = im.load()
    w, h = im.size
    mask = Image.new("L", (w, h))
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            R, G, B = px[x, y]
            hi, lo = max(R, G, B), min(R, G, B)
            sat = 0 if hi == 0 else (hi - lo) / hi
            mp[x, y] = max(0, min(255, int((sat - 0.07) / 0.11 * 255)))
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def keep_main_shape(im: Image.Image, seed: tuple[int, int]) -> Image.Image:
    """씨앗 점과 이어진 덩어리만 남긴다.

    잘라낸 영역 가장자리에 로고 글자("ell", "R") 조각이 걸려 들어오는데,
    작은 아이콘에서 이게 정체불명의 얼룩으로 보인다. 나무는 한 덩어리라 이걸로 깔끔히 분리된다.
    """
    alpha = im.split()[-1]
    w, h = alpha.size
    src = alpha.load()
    keep = Image.new("L", (w, h), 0)
    kp = keep.load()

    stack = [seed]
    seen = bytearray(w * h)
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        if src[x, y] < 40:  # 거의 투명하면 덩어리가 아니다
            continue
        kp[x, y] = src[x, y]
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    out = im.copy()
    out.putalpha(keep)
    return out


def square(im: Image.Image, pad_ratio: float = 0.05) -> Image.Image:
    box = im.split()[-1].getbbox()
    if box:
        im = im.crop(box)
    side = int(max(im.size) * (1 + pad_ratio * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def check(im: Image.Image, size: int, bg) -> Image.Image:
    tile = Image.new("RGBA", (size, size), bg)
    tile.alpha_composite(im.resize((size, size), Image.LANCZOS))
    return tile


def main() -> None:
    logo = cut_background(Image.open(SRC))
    cropped = logo.crop(SYMBOL_BOX)
    # 삼각형 테두리 위의 한 점을 씨앗으로 (가운데는 뚫려 있어 투명하다)
    seed = (cropped.width // 2, int(cropped.height * 0.93))
    print("씨앗 알파:", cropped.split()[-1].getpixel(seed))
    symbol = square(keep_main_shape(cropped, seed))
    print("심볼 크기:", symbol.size)

    DEST.parent.mkdir(exist_ok=True)
    symbol.save(DEST, format="ICO", sizes=[(s, s) for s in SIZES])
    print("저장:", DEST, f"({DEST.stat().st_size / 1024:.1f} KB)")

    # 실제 표시 크기 미리보기 — 밝은/어두운 배경 둘 다 (작업표시줄이 어두울 수 있다)
    scale = 6
    row_w = sum(s for s in SIZES if s <= 64) + 4 * 16
    preview = Image.new("RGBA", (row_w, 64 * 2 + 40), (255, 255, 255, 255))
    for row, bg in enumerate([(255, 255, 255, 255), (32, 32, 32, 255)]):
        x = 8
        for s in [s for s in SIZES if s <= 64]:
            preview.alpha_composite(check(symbol, s, bg), (x, 8 + row * 72 + (64 - s) // 2))
            x += s + 16
    preview.resize((preview.width * scale, preview.height * scale), Image.NEAREST).save(
        OUT / "icon_preview.png"
    )
    print("미리보기 저장: icon_preview.png")


if __name__ == "__main__":
    main()

