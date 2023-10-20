# general imports
import time
import board
import digitalio
import analogio
import terminalio
import touchio
import pwmio
import busio
import neopixel
import supervisor
import microcontroller
import os
import storage

import displayio
from adafruit_display_text import bitmap_label
from adafruit_bitmap_font import bitmap_font
import adafruit_imageload
import adafruit_ili9341 # display
from adafruit_display_shapes.rect import Rect

font_large = bitmap_font.load_font("/fonts/LiberationSans-Bold-140.pcf")
font_medium = bitmap_font.load_font("/fonts/LiberationSans-Bold-24.pcf")

welcome_text = "MAW Schlüsselkasten\n Buchungen auf Flink. \n  Bitte Code eingeben.  "
invalid_text = f"Code ungültig."

# DISPLAY SETUP
#

displayio.release_displays()

spi = busio.SPI(board.SCK, MOSI=board.MOSI)

display_bus = displayio.FourWire(spi, command=board.TX, chip_select=board.A4, reset=board.RX, baudrate=80000000)
display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)

backlight = pwmio.PWMOut(board.A5, frequency=2000, duty_cycle=int(1 * 65535))

# Make the display context
splash = displayio.Group()
#display = board.DISPLAY


logo, palette = adafruit_imageload.load("/images/logo.png", bitmap=displayio.Bitmap, palette=displayio.Palette)
pos_x = int(((display.width) - logo.width) / 2)
pos_y = int(((display.height) - logo.height) / 2)
logo_grid = displayio.TileGrid(logo, pixel_shader=palette, x=pos_x, y=pos_y)

rect = Rect(0, 0, 320, 240, fill=0xFFFFFF)

splash.append(rect)
splash.append(logo_grid)
display.show(splash)

# Draw some label text
rect2 = Rect(0, 0, 320, 240, fill=0xFFFFFF)
default = displayio.Group()
default.append(rect2)
code_label = bitmap_label.Label(font_large, text="", color=0x005060, x=2, y=60, width=300)
default.append(code_label)
status_label = bitmap_label.Label(font_medium, text=welcome_text, color=0x005060, anchor_point=(0.5,0.5), anchored_position=(160,180))
default.append(status_label)
display.show(default)

task1 = "entnehmen"
task2 = "entnommen"


status_label.text = f"Haben Sie etwas eingelegt\n        oder entnommen?\neingelegt:     entnommen:    "
status_label.text = f"Haben Sie den Inhalt\n      {task2}?\n    Ja:        Nein:     "

# prep icons
check, palette = adafruit_imageload.load("/images/check2.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
check_grid = displayio.TileGrid(check, pixel_shader=palette, x=115, y=203)
x, palette = adafruit_imageload.load("/images/X2.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
x_grid = displayio.TileGrid(x, pixel_shader=palette, x=292, y=203)
x_grid.x = 230
icons = displayio.Group()
icons.append(x_grid)
icons.append(check_grid)

default.append(icons)

while True:
    pass
