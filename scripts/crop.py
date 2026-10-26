"""crop.py <in.png> <out.png> <top> <height>  — crop a full-width screenshot (dev helper; needs pillow)."""
import sys
from PIL import Image
im = Image.open(sys.argv[1])
top, h = int(sys.argv[3]), int(sys.argv[4])
im.crop((0, top, im.width, min(im.height, top + h))).save(sys.argv[2], optimize=True)
