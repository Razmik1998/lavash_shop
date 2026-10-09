# Icon

`fishshop.ico` is a generated placeholder — a simple two-tone circle at
16/32/48/256px — not real branding. It exists purely so the icon wiring in
`packaging/pyinstaller/*.spec` and `packaging/installer/FishShop.iss`
(`SetupIconFile`, `UninstallDisplayIcon`) is exercised end-to-end and can be
swapped for a real logo later without touching the spec/installer files.

Regenerate or replace with:

```python
from PIL import Image, ImageDraw

sizes = [16, 32, 48, 256]
imgs = []
for size in sizes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([1, 1, size - 2, size - 2], fill=(30, 90, 160, 255))
    margin = max(2, size // 6)
    d.ellipse([margin, margin, size - margin, size - margin], fill=(230, 240, 250, 255))
    imgs.append(img)
imgs[-1].save(
    "packaging/assets/icon/fishshop.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=imgs[:-1],
)
```

To replace with real branding, drop in a new multi-resolution `.ico`
(16/32/48/256px recommended) at this same path — no other file needs to
change.
