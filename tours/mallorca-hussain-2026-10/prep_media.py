#!/usr/bin/env python3
"""Convert HEIC photos in ./media to .jpg (EXIF-rotated). Run once after copying Hussain's files into ./media."""
import glob, os, pillow_heif
from PIL import Image, ImageOps
pillow_heif.register_heif_opener()
d = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "media"))
for f in glob.glob(os.path.join(d, "*.HEIC")) + glob.glob(os.path.join(d, "*.heic")):
    out = os.path.splitext(f)[0] + ".jpg"
    if not os.path.exists(out):
        ImageOps.exif_transpose(Image.open(f)).convert("RGB").save(out, quality=92); print("converted", os.path.basename(out))
