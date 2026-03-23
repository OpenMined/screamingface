#!/usr/bin/env python3
"""Generate Electron app icons from the 😱 emoji using macOS native rendering.

Produces:
  build/icon.icns  — macOS
  build/icon.ico   — Windows
  build/icon.png   — Linux (512x512)

Requirements: Pillow, pyobjc-framework-Cocoa (pip install Pillow pyobjc-framework-Cocoa)
Run: python apps/desktop/scripts/generate-icon.py
"""

import subprocess
import tempfile
from pathlib import Path

# --- macOS native rendering via PyObjC ---
import AppKit  # pyobjc-framework-Cocoa
import Cocoa  # pyobjc-framework-Cocoa
from PIL import Image  # Pillow

EMOJI = "\U0001f631"  # 😱
SIZE = 1024
BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

# Sizes needed for .iconset (each also has a @2x variant at double resolution)
ICONSET_SIZES = [16, 32, 64, 128, 256, 512]
ICO_SIZES = [16, 32, 48, 64, 128, 256]


def render_emoji_to_png(size: int) -> Image.Image:
    """Render the emoji at the given pixel size using Apple Color Emoji."""
    # Create a bitmap context
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, AppKit.NSCalibratedRGBColorSpace, 0, 0
    )
    context = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    AppKit.NSGraphicsContext.setCurrentContext_(context)

    # Clear to transparent
    Cocoa.NSColor.clearColor().set()
    AppKit.NSRectFill(((0, 0), (size, size)))

    # Use Apple Color Emoji font, sized to fill the canvas with some padding
    font_size = size * 0.78
    font = AppKit.NSFont.fontWithName_size_("Apple Color Emoji", font_size)
    if font is None:
        raise RuntimeError("Apple Color Emoji font not found")

    attrs = {
        AppKit.NSFontAttributeName: font,
    }
    ns_string = AppKit.NSAttributedString.alloc().initWithString_attributes_(
        EMOJI, attrs
    )

    # Measure the string to center it
    string_size = ns_string.size()
    x = (size - string_size.width) / 2
    y = (size - string_size.height) / 2
    ns_string.drawAtPoint_((x, y))

    context.flushGraphics()
    AppKit.NSGraphicsContext.setCurrentContext_(None)

    # Convert to PNG bytes, then to Pillow Image
    png_data = rep.representationUsingType_properties_(
        AppKit.NSBitmapImageFileTypePNG, {}
    )
    import io

    return Image.open(io.BytesIO(png_data)).convert("RGBA")


def create_icns(base_image: Image.Image, output_path: Path) -> None:
    """Create .icns file via iconutil from a base 1024x1024 image."""
    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = Path(tmpdir) / "icon.iconset"
        iconset_dir.mkdir()

        for s in ICONSET_SIZES:
            # Standard resolution
            img = base_image.resize((s, s), Image.LANCZOS)
            img.save(iconset_dir / f"icon_{s}x{s}.png")
            # @2x (Retina) resolution
            img2x = base_image.resize((s * 2, s * 2), Image.LANCZOS)
            img2x.save(iconset_dir / f"icon_{s}x{s}@2x.png")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
            check=True,
        )


def create_ico(base_image: Image.Image, output_path: Path) -> None:
    """Create .ico file with multiple sizes."""
    sizes = [(s, s) for s in ICO_SIZES]
    base_image.save(str(output_path), format="ICO", sizes=sizes)


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Rendering {EMOJI} at {SIZE}x{SIZE} using Apple Color Emoji...")
    base = render_emoji_to_png(SIZE)

    print("Creating icon.icns (macOS)...")
    create_icns(base, BUILD_DIR / "icon.icns")

    print("Creating icon.ico (Windows)...")
    create_ico(base, BUILD_DIR / "icon.ico")

    print("Creating icon.png (Linux, 512x512)...")
    linux_icon = base.resize((512, 512), Image.LANCZOS)
    linux_icon.save(BUILD_DIR / "icon.png")

    print(f"Done! Icons written to {BUILD_DIR}/")


if __name__ == "__main__":
    main()
