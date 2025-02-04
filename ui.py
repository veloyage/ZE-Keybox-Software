#
# Schlüsselkasten UI/DISPLAY SETUP
#

import board
import busio
import pwmio
import fourwire
import displayio
import time
import microcontroller

from adafruit_display_text import bitmap_label
from adafruit_bitmap_font import bitmap_font
# import terminalio
import adafruit_imageload
import adafruit_ili9341  # display
from adafruit_display_shapes.rect import Rect

displayio.release_displays()

from hardware import LED_internal, LED_connector_1, LED_connector_2, backlight, haptic, read_keypad

# import adafruit_miniqr

# version string
version = "1.2.0"

text_color = 0x005050

spi = busio.SPI(board.SCK, MOSI=board.MOSI)

display_bus = fourwire.FourWire(spi, command=board.TX, chip_select=board.A4, reset=board.RX, baudrate=80000000)
display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)

splash = displayio.Group()
# display = board.DISPLAY

font_large = bitmap_font.load_font("/fonts/LiberationSans-Bold-140.pcf")
font_medium = bitmap_font.load_font("/fonts/LiberationSans-Bold-24.pcf")
font_small = bitmap_font.load_font("/fonts/LiberationSans-Bold-10.pcf")

logo, palette = adafruit_imageload.load("/images/logo.png", bitmap=displayio.Bitmap, palette=displayio.Palette)
pos_x = int(((display.width) - logo.width) / 2)
pos_y = int(((display.height) - logo.height) / 2)
logo_grid = displayio.TileGrid(logo, pixel_shader=palette, x=pos_x, y=pos_y)

rect = Rect(0, 0, 320, 240, fill=0xFFFFFF)

splash.append(rect)
splash.append(logo_grid)

log_labels = [None] * 5
next_label = 0

for index, label in enumerate(log_labels):
    log_labels[index] = bitmap_label.Label(font_small, text="", color=text_color, x=2, y=180+12*index)
    splash.append(log_labels[index])

display.root_group = splash

# prep icons
no_flink, palette = adafruit_imageload.load("/images/cloud_off.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
no_flink_grid = displayio.TileGrid(no_flink, pixel_shader=palette, x=10, y=0)
no_flink_grid.hidden = True
no_wifi, palette = adafruit_imageload.load("/images/wifi_off.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
no_wifi_grid = displayio.TileGrid(no_wifi, pixel_shader=palette, x=50, y=0)
no_wifi_grid.hidden = True
warning, palette = adafruit_imageload.load("/images/warning.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
warning_grid = displayio.TileGrid(warning, pixel_shader=palette, x=130, y=0)
warning_grid.hidden = True
maintainance, palette = adafruit_imageload.load("/images/maintainance.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
maintainance_grid = displayio.TileGrid(maintainance, pixel_shader=palette, x=170, y=0)
maintainance_grid.hidden = True
low_battery, palette = adafruit_imageload.load("/images/battery_very_low.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
low_battery_grid = displayio.TileGrid(low_battery, pixel_shader=palette, x=250, y=0)
low_battery_grid.hidden = True
no_power, palette = adafruit_imageload.load("/images/power_off.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
no_power_grid = displayio.TileGrid(no_power, pixel_shader=palette, x=290, y=0)
no_power_grid.hidden = True

# open all compartments
def open_all(compartments):
    for index in range(len(compartments)):
        compartments[str(index + 1)].open()
        microcontroller.watchdog.feed() # feed the watchdog

def main():
    # use global keyword to access UI elements, not the prettiest way of doing it
    global code_label, status_label, icons1, icons2, no_flink_grid, no_wifi_grid, maintainance_grid, warning_grid, no_power_grid, low_battery_grid, welcome_text, invalid_text

    welcome_text = "MAW Schlüsselkasten\n Buchungen auf Flink. \n  Bitte Code eingeben.  "
    invalid_text = "     Code ungültig.      \n     Bitte überprüfe     \nBuchung und Uhrzeit."

    # Draw some labels
    rect2 = Rect(0, 0, 320, 240, fill=0xFFFFFF)
    main = displayio.Group()
    main.append(rect2)
    code_label = bitmap_label.Label(font_large, text="", color=text_color, x=4, y=67, width=300)
    main.append(code_label)
    status_label = bitmap_label.Label(font_medium, text=welcome_text, color=text_color, anchor_point=(0.5, 0.5), anchored_position=(160, 185))
    main.append(status_label)

    main.append(no_flink_grid)
    main.append(no_wifi_grid)
    main.append(maintainance_grid)
    main.append(warning_grid)
    main.append(no_power_grid)
    main.append(low_battery_grid)

    check, check_palette = adafruit_imageload.load("/images/check.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
    check_grid = displayio.TileGrid(check, pixel_shader=check_palette, x=220, y=177)
    x, x_palette = adafruit_imageload.load("/images/X.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
    x_grid = displayio.TileGrid(x, pixel_shader=x_palette, x=242, y=207)
    icons1 = displayio.Group()
    icons1.append(x_grid)
    icons1.append(check_grid)
    icons1.hidden = True
    main.append(icons1)

    check2_grid = displayio.TileGrid(check, pixel_shader=check_palette, x=240, y=207)
    x2_grid = displayio.TileGrid(x, pixel_shader=x_palette, x=150, y=207)
    icons2 = displayio.Group()
    icons2.append(x2_grid)
    icons2.append(check2_grid)
    icons2.hidden = True
    main.append(icons2)

    display.root_group = main


# deal with compartment open/close logic
def process_compartment(compartments, compartment_index, logger):
    # code valid
    if compartment_index is not None:
        if compartment_index in compartments:
            compartments[compartment_index].set_LEDs((50,50,50))
            LED_internal.fill((15,50,0))
            status_label.text = f"Fach {compartment_index} wird geöffnet."
            time.sleep(1) # wait a second for the user to read
            status = compartments[compartment_index].open(1)
            if compartments[compartment_index].content_status == "present":
                task1 = "entnehmen"
                task2 = "entnommen"
            elif compartments[compartment_index].content_status == "empty":
                task1 = "einlegen"
                task2 = "eingelegt"
            else:
                instruction = "einlegen/entnehmen"
            # successfully opened
            if status == True:
                status_label.text = f"Bitte Inhalt entnehmen\n    oder zurücklegen  \nund Fach {compartment_index} schliessen."
                time.sleep(1) # wait a second for the user to read
            # not successfully opened, try again
            else:
                status_label.text = f"Fach blockiert?\nBitte drücke\n leicht auf Fach {compartment_index}."
                time.sleep(5) # wait for the user to read and check
                status = compartments[compartment_index].open(3)
                if status == True: # successfully opened
                    status_label.text = f"Bitte Inhalt entnehmen\n  oder zurücklegen  \nund Fach {compartment_index} schliessen."
                else:
                    status_label.text = f"Fach öffnet sich nicht.\nBitte erneut versuchen,\noder Alternative buchen."
                    logger.error(f"Door {compartment_index} did not open.")
                    time.sleep(8) # wait for user to read
            # wait for user to close door
            counter = 600
            while compartments[compartment_index].get_inputs() == True and counter > 0:
                time.sleep(0.1)
                counter -= 1
                reply = read_keypad()
                if reply == "x":
                    counter = 0 # break loop and treat is as no answer
                microcontroller.watchdog.feed() # feed the watchdog
            if counter == 0:
                logger.warning(f"Door {compartment_index} not closed.")
                compartments[compartment_index].door_status = "open"
            else:
                compartments[compartment_index].door_status = "closed"

            # ask for content status
            counter = 600
            if compartments[compartment_index].content_status == "unknown":
                status_label.text = f"      Hast du etwas  \n    zurückgelegt (    )\noder entnommen (    )?"
                icons1.hidden = False
            else:
                status_label.text = f"Hast du den Inhalt\n      {task2}?\n    Nein:        Ja:     "
                icons2.hidden = False
            while counter > 0:
                time.sleep(0.1)
                counter -= 1
                microcontroller.watchdog.feed() # feed the watchdog
                reply = read_keypad()
                if reply == "✓":
                    haptic.play()
                    if compartments[compartment_index].content_status == "unknown" or compartments[compartment_index].content_status == "empty":
                        compartments[compartment_index].content_status = "present"
                    else:
                        compartments[compartment_index].content_status = "empty"
                    break
                elif reply == "x":
                    haptic.play()
                    if compartments[compartment_index].content_status == "unknown" or compartments[compartment_index].content_status == "empty":
                        compartments[compartment_index].content_status = "empty"
                    else:
                        compartments[compartment_index].content_status = "present"
                    break
            if counter == 0:
                logger.warning(f"User did not answer status question.")
                compartments[compartment_index].content_status = "unknown"

            # reset UI
            icons1.hidden = True
            icons2.hidden = True
            compartments[compartment_index].set_LEDs((0,0,0))
        elif compartment_index == "99":
            LED_internal.fill((15,50,0))
            status_label.text = f"Alle Fächer werden geöffnet."
            open_all(compartments)
        else:
            logger.warning(f"Code valid for non-existent / not connected compartment.")
            LED_internal.fill((90,0,0))
            status_label.text="      Code ist für nicht      \nverbundenes/eingerichtetes\n      Fach bestimmt.      "
            time.sleep(3)
    # code invalid
    else:
        LED_internal.fill((90,0,0))
        status_label.text=invalid_text
        time.sleep(3)

    LED_internal.fill((30,30,30))
    code_label.text = ""
    status_label.text=welcome_text
