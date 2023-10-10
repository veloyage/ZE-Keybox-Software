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
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
import adafruit_imageload
import adafruit_ili9341 # display
from adafruit_display_shapes.rect import Rect


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


logo, palette = adafruit_imageload.load("/images/logo.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
pos_x = int(((display.width) - logo.width) / 2)
pos_y = int(((display.height) - logo.height) / 2)
logo_grid = displayio.TileGrid(logo, pixel_shader=palette, x=pos_x, y=pos_y)

rect = Rect(0, 0, 320, 240, fill=0xFFFFFF)

splash.append(rect)
splash.append(logo_grid)
display.show(splash)

while True:
    pass

