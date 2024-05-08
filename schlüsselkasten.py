# Ziemann Engineering Schlüsselkasten-Software
# main code file

# SPDX-FileCopyrightText: 2023 Thomas Ziemann for Ziemann Engineering
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Changelog:
# 0.1: initial hardware test version, major TODOs: flink connection, key pickup/return logic, display UI, logging
# 0.2: added display, logging, initial readout and key logic
# 0.3: added keypad readout, more key logic, working compartment interface
# 0.4: dealing with content and door logic, adding regular keepalives, check accelerometer and light sensor
# 0.5: logging to screen during startup, codes are always strings, compartments are a dict and the index is a char starting at '1', touch matrix handling shortened
# 0.9: testing version, several small updates over 0.5, including new small font and better touch cal filtering
# 0.9.1: test version, touchpad individual buttons via MPR121 instead of native matrix
# 0.9.2: test version, battery monitor is optional, adafruit/TLS issues trigger a reconnect
# 0.9.3: test version, switched to adafruit HTTP API and made calls to update only every minute instead of every second, improved handling of missing wifi / connection issues, maintainances codes are not printed
# 0.9.4: bugfixes, commented sections removed, CP9.0 compatible

# TODO: add OTA updating, reorganize/push code into separate classes or files, icons for missing wifi, flink or mains power (battery status), reconnect to wifi if connection lost

# general imports
import time
import board
import digitalio
#import analogio
#import touchio
import pwmio
import busio
import neopixel
import supervisor
import sys
import microcontroller
import watchdog
import os
import storage

import ipaddress
import ssl
import wifi
import socketpool
import rtc
import adafruit_requests
import adafruit_ntp

import displayio
import fourwire
from adafruit_display_text import bitmap_label
from adafruit_bitmap_font import bitmap_font
#import terminalio
import adafruit_imageload
import adafruit_ili9341 # display
from adafruit_display_shapes.rect import Rect

import adafruit_miniqr
import adafruit_logging as logging

from adafruit_mcp230xx.mcp23017 import MCP23017 # port expander
import adafruit_lis3dh # accelerometer
from adafruit_ltr329_ltr303 import LTR329 # light sensor
import adafruit_drv2605 # haptic driver
from adafruit_max1704x import MAX17048 # battery monitor
import adafruit_mpr121 # touch sensor


import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_io.adafruit_io import IO_MQTT, IO_HTTP
import adafruit_logging as logging

import compartment

# version string
version = "0.9.4"

# enable watchdog to reset on error
#wd = microcontroller.watchdog
#wd.timeout = 30
#wd.mode = watchdog.WatchDogMode.RESET

#
# LOAD VARIABLES
#

ID = os.getenv("ID")
SN = os.getenv("SN")

compartment_number_saved = os.getenv("COMPARTMENT_NUMBER")
large_compartments = os.getenv("LARGE_COMPARTMENTS").split()

maintainance_code = os.getenv("MAINTAINANCE_CODE_PREFIX")

wifi_ssid = os.getenv("CIRCUITPY_WIFI_SSID")
wifi_pw = os.getenv("CIRCUITPY_WIFI_PASSWORD")

aio_username = os.getenv("ADAFRUIT_IO_USERNAME")
aio_key = os.getenv("ADAFRUIT_IO_KEY")
aio_feed_name = os.getenv("ADAFRUIT_IO_FEED")

tamper_alarm = os.getenv("TAMPER_ALARM")

#
# FLINK SETUP
#

flink_URL = os.getenv("FLINK_URL")
flink_API_key = os.getenv("FLINK_API_KEY")

# prepare for internet things
if not wifi.radio.connected:
    try:
        wifi.radio.connect(wifi_ssid, wifi_pw)
    except Exception:
        pass

pool = socketpool.SocketPool(wifi.radio)

requests = adafruit_requests.Session(pool, ssl.create_default_context())

# send status to Flink
def put_status():
    try:
        response = requests.put(f"{flink_URL}/{ID}/status", headers={"Authorization": flink_API_key}, json={"time": format_time(), "uptime": f"{time.monotonic()}",
            "serial": f"{SN}", "version": f"{version}", "compartments": f"{compartment_number_saved}", "large_compartments": f"{large_compartments}"}, timeout=1.5)
        return response.status_code
    except Exception as e:
        logger.error(f"Error putting status: {e}")
        return e

# get codes from Flink
def get_codes():
    try:
        response = requests.get(f"{flink_URL}/{ID}/codes", headers={"Authorization": flink_API_key}, timeout=1.5)
        return response.status_code, response.json()
    except Exception as e:
        logger.error(f"Error getting codes: {e}")
        return e, None

def post_code_log(code, compartment_index):
    if (compartment_index is not None) and (compartment_index in compartments):
        content = compartments[compartment_index].content_status
        door = compartments[compartment_index].door_status
    else:
        content = None
        door = None
    try:
        response = requests.post(f"{flink_URL}/{ID}/code_log", headers={"Authorization": flink_API_key}, json={"time": format_time(),
                                        "code_entered": f"{code}", "compartment": f"{compartment_index}", "content": content, "door": door}, timeout=1.5)
        return response.status_code
    except Exception as e:
        logger.error(f"Error posting code log: {e}")
        return e


class FlinkLogHandler(logging.Handler):
    def emit(self, record):
        try:
            response = requests.post(f"{flink_URL}/{ID}/error_log", headers={"Authorization": flink_API_key}, json={"time": format_time(), "uptime": f"{record.created}", "level": f"{record.levelname}", "message": f"{record.msg}"}, timeout=1.5)
        except Exception: # ignore, otherwise we will get another error while logging
            pass

#
# DISPLAY SETUP
#

displayio.release_displays()

spi = busio.SPI(board.SCK, MOSI=board.MOSI)

display_bus = fourwire.FourWire(spi, command=board.TX, chip_select=board.A4, reset=board.RX, baudrate=40000000)
display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)

backlight = pwmio.PWMOut(board.A5, frequency=2000, duty_cycle=int(1 * 65535))

# Make the display context
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

log_label_count = 5
log_labels = []
for x in range(log_label_count):
    log_labels.append(bitmap_label.Label(font_small, text="", color=0x006060, x=2, y=180+12*x))
    splash.append(log_labels[x])

next_label = 0

display.root_group = splash

#
# LOGGING SETUP
#

# try to get the time from the internet
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=2)
    rtc.RTC().datetime = ntp.datetime
except:
    online = False

# Initialize log functionality
logger = logging.getLogger("schlüsselkasten_log")
logger.setLevel(logging.INFO)

def format_time():
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02}-{t.tm_mday:02}_{t.tm_hour:02}-{t.tm_min:02}-{t.tm_sec:02}"

# prepare local file logging
if time.localtime().tm_year < 2023: # time incorrect, likely not set due to missing internet connection
    filename = "/logs/unknown_time.log"
else:
    t = time.localtime()
    filename = f"/logs/{format_time()}.log"

# check if we have storage access and if so, open local logfile
try:
    storage.remount("/", False)
    file_handler = logging.FileHandler(filename)
    logger.addHandler(file_handler)
    logger.info("Logging to local file started.")
    local_logging = True
except (OSError, RuntimeError) as e:  # When the filesystem is NOT writable, it's likely due to being connected to a computer -> log to console
    local_logging = False
    #if e.args[0] == 28: # filesystem full
    stream_handler = logging.StreamHandler()
    logger.addHandler(stream_handler)
    logger.info(e) # send error as info, as it may occur regularly and is handled
    logger.info("Filesystem not writeable, logging to shell started.")

# check if we have internet
try:
    ping_ip = ipaddress.IPv4Address("8.8.8.8")
    ping = wifi.radio.ping(ip=ping_ip)
    if ping == None:
        raise Exception("Ping failed.")
    online = True
except Exception as e:
    logger.error(e)
    online = False

# process received command
def process_command(payload):
        #print(payload)
        payload = payload.split(" ")
        command = payload[0]
        if command == "status" and len(payload) == 2:
            comp = payload[1]
            if comp == "all":
                logger.info(f"Open compartments: {check_all()}")
            elif int(comp) > 0 and int(comp) <= len(compartments):
                logger.info(f"Compartment {comp} status: door open: {compartments[comp].get_inputs()}, door status saved: {compartments[comp].door_status}, content status: {compartments[comp].content_status}.")
        elif command == "open" and len(payload) == 2:
            comp = payload[1]
            if comp == "all":
                open_all()
            elif int(comp) > 0 and int(comp) <= len(compartments):
                compartments[comp].open()
            logger.info(f"Compartment open sent from Adafruit IO: {comp}")
        elif command == "reset" and len(payload) == 1:
            microcontroller.reset()
        elif command == "tamper_alarm" and len(payload) == 2:
            global tamper_alarm
            if payload[1] == "off":
                tamper_alarm = "off"
            elif payload[1] == "on":
                tamper_alarm = "on"


class AIOLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    io.publish(aio_feed_name + "status", self.format(record))
                except Exception as e: # ignore exception, logging would trigger further exceptions
                    print(e)
                    pass

class DisplayLogHandler(logging.Handler):
            def emit(self, record):
                global log_labels, next_label
                log_labels[next_label].text = record.msg
                next_label += 1
                if next_label == log_label_count:
                    next_label = 0
display_log = DisplayLogHandler()
logger.addHandler(display_log)

# Callback function which will be called when a connection is established
def connected(client):
    client.subscribe(aio_feed_name + "command")

# Callback function which will be called when a message comes from a subscribed feed
def message(client, feed_id, payload):
    if feed_id == (aio_feed_name + "command"):
        process_command(payload)

# if we have internet, connect to adafruit IO and use it for logging
if online:
    # Initialize a new MQTT Client object
    mqtt_client = MQTT.MQTT(broker="io.adafruit.com", port=8883, is_ssl=True, username=aio_username, password=aio_key, socket_pool=pool, ssl_context=ssl.create_default_context())
    try:
        # Initialize an Adafruit IO MQTT Client
        io = IO_MQTT(mqtt_client)
        # Set up the callback methods above
        io.on_connect = connected
        io.on_message = message
        io.connect()

        logger.addHandler(AIOLogHandler())
        logger.info("Logging to Adafruit IO started.")
    except Exception as e:
        logger.error(f"Error connecting to Adafruit IO: {e}")

    flink_log_handler = FlinkLogHandler(logging.ERROR)
    logger.addHandler(flink_log_handler)
    logger.info("Logging to Flink started.")

# read processor UID and format it as hex-string (like it is in the boot_out.txt)
def hex_format(hex_in):
    string = ""
    for x in hex_in:
        string += f"{x:0{2}X}"
    return string
#
# INFO MESSAGES
#
logger.info(f"Ziemann Engineering Schlüsselkasten {ID}")
logger.info(f"Serial number {SN}, compartments: {compartment_number_saved}, large compartments: {large_compartments}")
logger.info(f"Software version {version}, CircuitPython version: {sys.implementation.version[0]}.{sys.implementation.version[1]}.{sys.implementation.version[2]}")

reset_reason = microcontroller.cpu.reset_reason
logger.info(f"CPU ID: {hex_format(microcontroller.cpu.uid)}, temperature: {microcontroller.cpu.temperature:.2}°C")
logger.info(f"Last reset reason: {str(microcontroller.cpu.reset_reason).split('.')[2]}, supervisor run reason: {str(supervisor.runtime.run_reason).split('.')[2]}")
if wifi.radio.connected:
    logger.info(f"Wifi connected to {wifi.radio.ap_info.ssid}, RSSI: {wifi.radio.ap_info.rssi}.")
else:
    logger.warning("Wifi not connected.")
logger.info(f"IP address: {wifi.radio.ipv4_address}, MAC: {hex_format(wifi.radio.mac_address)}")

if ping is not None:
    logger.info(f"Ping to google: {ping*1000} ms.")
else:
    logger.warning(f"Ping to google failed.")

status_code = put_status()
if status_code == 200:
    logger.info(f"Response from Flink: {status_code}.")
else:
    logger.warning(f"Response from Flink: {status_code}.")
#
# HARDWARE SETUP
#
# set up 12V enable pin
enable_12V = digitalio.DigitalInOut(board.A3)
enable_12V.direction = digitalio.Direction.OUTPUT
enable_12V.value = False

## LED config
LED_internal = neopixel.NeoPixel(board.A2, 6)
LED_connector_1 = neopixel.NeoPixel(board.A1, 32)
LED_connector_2 = neopixel.NeoPixel(board.A0, 32)

# piezo buzzer
piezo = pwmio.PWMOut(board.MISO, frequency=1000, duty_cycle=0)

## I2C init
i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)

try:
    haptic = adafruit_drv2605.DRV2605(i2c) # 0x5A
    haptic.use_LRM()
    haptic.sequence[0] = adafruit_drv2605.Effect(1) # effect 1: strong click, 4: sharp click, 24: sharp tick,  27: short double click strong, 16: 1000 ms alert
except Exception as e:
    haptic = None
    logger.error(f"Error setting up haptic engine: {e}")

try:
    accelerometer = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x19)
except Exception as e:
    accelerometer = None
    logger.error(f"Error setting up accelerometer: {e}")

try:
    light_sensor = LTR329(i2c) # 0x29
except Exception as e:
    light_sensor = None
    logger.error(f"Error setting up brightness sensor: {e}")

try: # some boards have a different or no battery monitor, deal with it
    battery_monitor = MAX17048(i2c) # 0x36
except Exception:
    battery_monitor = None
    logger.error(f"Error setting up battery monitor: {e}")

try:
    touch_sensor = adafruit_mpr121.MPR121(i2c, address=0x5B) # 0x5B, ADDR to VCC / close jumper
except Exception as e:
    touch_sensor = None
    logger.error(f"Error setting up touch sensor: {e}")

# also on the bus at 0x38: touch screen controller FT6206

# get connected port expanders (adresses from 0x20 to 0x27, prototype PCBs: 0x24 to 0x27)
port_expanders = []
for addr in range(0x20, 0x28):
    try:
        port_expanders.append(MCP23017(i2c, address=addr))
    except: # ValueError if device does not exist, ignore
        pass

# calculate which spaces the large compartments take up.
# spaces = spots/port expander connections where individual compartments could be
# spaces formula: expander_index * 8 + compartment_per_expander + 1
#large_compartment_spaces = {}
for index in large_compartments:
    space = int(index) # TODO?: only works for first large compartment
large_compartment_spaces = [space, space+1, space+8, space+9]

# create compartment objects with IO ports, and a dict for all of them
compartments = {}
counter = 1
for index, expander in enumerate(port_expanders):
    for compartment_per_expander in range(8):
        space = index * 8 + compartment_per_expander + 1
        # large compartment handling
        if space in large_compartment_spaces:
            pos = large_compartment_spaces.index(space)
            if pos == 0: # first space: create comp as normal
                pass # skip to normal part
            elif pos == 1 or pos == 3: # second, fourth space: add LED to first
                compartments[str(large_compartment_spaces[0])].LEDs.append(LED_connector_1[space-1])
                continue
            elif pos == 2: # third space: add IO to first, also LED
                compartments[str(large_compartment_spaces[0])].add_input(expander.get_pin(compartment_per_expander*2))
                compartments[str(large_compartment_spaces[0])].add_output(expander.get_pin(compartment_per_expander*2+1))
                compartments[str(large_compartment_spaces[0])].LEDs.append(LED_connector_1[space-1])
                continue
        # normal compartments
        input_pin = expander.get_pin(compartment_per_expander*2)
        output_pin = expander.get_pin(compartment_per_expander*2+1)
        new_compartment = compartment.compartment(input_pin, output_pin)
        new_compartment.LEDs = [LED_connector_1[space-1]]
        compartments[f"{counter}"] = new_compartment
        counter += 1

if battery_monitor is not None:
    logger.info(f"Battery status: {battery_monitor.cell_voltage:.2f}V, {battery_monitor.cell_percent:.1f} %")

logger.info(f"{len(port_expanders)} compartment PCBs / rows detected.")
if len(compartments) < compartment_number_saved:
    logger.error(f"Insufficient compartment PCBs detected")

# open all compartments
def open_all():
    for index in range(len(compartments)):
        compartments[str(index+1)].open()

# check door of all compartments
def check_all():
    open_comps = []
    for index in range(len(compartments)):
        if compartments[str(index+1)].get_inputs():
            open_comps.append(str(index+1))
    return open_comps

open_comps = check_all()
if len(open_comps) is not 0:
    logger.warning(f"Open compartments: {open_comps}")

keys = ["1","2","3","4","5","6","7","8","9","x","0","✓"]

# read touch pads with MPR121
def read_mpr121():
    touched_list = []
    touched = touch_sensor.touched()
    for i in range(12):
        if touched & (1 << i):
           touched_list.append(i)
    if len(touched_list) == 1: # only if exactly one button is pressed
        return keys[touched_list[0]] # assumes pads are wired sequentially
    else:
        return None

logger.removeHandler(display_log) # stop logging to display

welcome_text = "MAW Schlüsselkasten\n Buchungen auf Flink. \n  Bitte Code eingeben.  "
invalid_text = f"     Code ungültig.      \n     Bitte überprüfe     \nBuchung und Uhrzeit."

# Draw some label text
rect2 = Rect(0, 0, 320, 240, fill=0xFFFFFF)
default = displayio.Group()
default.append(rect2)
code_label = bitmap_label.Label(font_large, text="", color=0x006060, x=2, y=60, width=300)
default.append(code_label)
status_label = bitmap_label.Label(font_medium, text=welcome_text, color=0x006060, anchor_point=(0.5,0.5), anchored_position=(160,180))
default.append(status_label)
display.root_group = default

# prep icons
check, palette = adafruit_imageload.load("/images/check.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
check_grid = displayio.TileGrid(check, pixel_shader=palette, x=115, y=203)
x, palette = adafruit_imageload.load("/images/X.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette)
x_grid = displayio.TileGrid(x, pixel_shader=palette, x=292, y=203)
icons = displayio.Group()
icons.append(x_grid)
icons.append(check_grid)

#debug: valid_codes = {'1': ["1234", "1235"], '2':["2345", "2346"], '3':["3456", "3457"]}

LED_internal.fill((30,30,30))

# check if given code is in dict of valid codes, or a maintainance code
def check_code(code):
    if len(code) == 4: # normal codes have 4 digits
        status_code, valid_codes = get_codes() # get codes from Flink
        if status_code is not 200:
            logger.error(f"Error response from Flink when getting codes: {status_code}")
        if valid_codes is not None:
            for comp, comp_codes in valid_codes.items():
                if code in comp_codes:
                    return comp, False
        return None, False
    elif len(code) == 8: # maintainance codes have 8 digits
        if code[2:8] == maintainance_code:
            comp = int(code[0:2])
            code = "maintainance"
            return str(comp), True # converted string to int and back to remove leading zeros
        else:
            return None, True
    else:
        return None, False

# deal with compartment open/close logic
def process_compartment(compartment_index):
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
                status_label.text = f"Bitte Inhalt entnehmen\n  oder zurücklegen  \nund Fach {compartment_index} schliessen."
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
                reply = read_mpr121() # read_matrix()
                if reply == "x":
                    counter = 0 # break loop and treat is as no answer
                #wd.feed() # feed the watchdog
            if counter == 0:
                logger.warning(f"Door {compartment_index} not closed.")
                compartments[compartment_index].door_status = "open"
            else:
                compartments[compartment_index].door_status = "closed"

            # ask for content status
            counter = 600
            default.append(icons)
            if compartments[compartment_index].content_status == "unknown":
                status_label.text = f"   Hast du etwas eingelegt\n        oder entnommen?\neingelegt:     entnommen:    "
                x_grid.x = 292
            else:
                status_label.text = f"Hast du den Inhalt\n      {task2}?\n    Ja:        Nein:     "
                x_grid.x = 230
            while counter > 0:
                time.sleep(0.1)
                counter -= 1
                #wd.feed() # feed the watchdog
                reply = read_mpr121() # read_matrix()
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
            default.remove(icons)
            compartments[compartment_index].set_LEDs((0,0,0))
        elif compartment_index == "99":
            LED_internal.fill((15,50,0))
            status_label.text = f"Alle Fächer werden geöffnet."
            open_all()
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
    status_label.text=welcome_text

#
# Normal operation
#
#wd.timeout = 10
pressed_count = 1
last_pressed = None
buffer = [None] * pressed_count
i = 0
code = ""
counter = 0

while True:
    # buffer[i] = read_matrix() # read into buffer
    buffer[i] = read_mpr121() # read into buffer
    if len(set(buffer)) == 1: # if all buffer elements are the same
        if buffer[i] != last_pressed:
            last_pressed = buffer[i]
            if buffer[i] is not None:
                haptic.play()
                button = buffer[i]
                if button is "✓": # process input
                    compartment_index, maintainance = check_code(code) # check if the code is in the list and return the compartment index if yes, None if not
                    process_compartment(compartment_index)
                    if maintainance:
                        code = "maintainance"
                    # Flink code log
                    response = post_code_log(code, compartment_index)
                    if (compartment_index is not None) and (compartment_index in compartments):
                        logger.info(f"Code '{code}' was entered, valid for compartment {compartment_index}, content status: {compartments[compartment_index].content_status}, door status: {compartments[compartment_index].door_status}.")
                        # after logging, set status back to unknown - we do not want to rely on the user answering correctly/truthfully. TODO?: this makes part of the status query code useless, remove?
                        compartments[compartment_index].content_status = "unknown"
                    elif compartment_index == "99":
                        logger.info(f"Maintainance code to open all compartments was entered.")
                    else:
                        logger.info(f"Code '{code}' was entered, invalid")
                    code = ""
                    code_label.text = code
                elif button is "x": # clear input
                    code = ""
                    code_label.text = code
                elif len(code) < 8: # add number to code, ignore anything above 8 chars
                    code = code + button
                    if len(code) <= 4:
                        code_label.text = code

    # handle index
    i += 1
    if i == pressed_count:
        i = 0

    if accelerometer is not None and tamper_alarm == "on":
        x, y, z = accelerometer.acceleration # in m/s2
        if abs(z) > 1:  # check accelerometer
            # TODO: message on screen
            LED_internal.fill((255,0,0))
            piezo.duty_cycle = int(0.5*65536)
        else:
            LED_internal.fill((0,0,0))
            piezo.duty_cycle = 0

    if counter%300 == 0: # runs roughly every 15 s
        # wd.feed() # feed the watchdog, TODO: after 5 s it will reset
        try:
            io.loop(timeout=1) # get updates from adafruit IO
        except Exception as e:
            logger.error(f"Error getting update from Adafruit IO: {e}")
            io.reconnect()

        if light_sensor is not None:
            try:
                light = light_sensor.visible_plus_ir_light - light_sensor.ir_light   # check brightness
                if light <= 100: # > 100 is relatively bright, > 1000 very bright
                    if light < 0:
                        light = 0
                    backlight.duty_cycle = int((0.3+0.7*light/100)*65535)
                    LED_internal.brightness = 0.3+0.7*light/100
                    LED_connector_1.brightness = 0.3+0.7*light/100
                    LED_connector_2.brightness = 0.3+0.7*light/100
                else:
                    backlight.duty_cycle = int(1*65535)
                    LED_internal.brightness = 1
                    LED_connector_1.brightness = 1
                    LED_connector_2.brightness = 1
            except Exception as e:
                logger.error(f"Error getting ambient brightness: {e}")

    if counter == 6000: # runs roughly every 5 minutes
        counter = 0
        put_status() # send status as keepalive
        if battery_monitor is not None:
            if battery_monitor.cell_percent < 30 or battery_monitor.cell_voltage < 3.5: # log if low battery
                logger.warning(f"Battery low: {battery_monitor.cell_voltage:.2f}V, {battery_monitor.cell_percent:.1f} %")
        # regularly reset device, eg at 3 AM. if time says 3 and runtime is > 3:20 h -> reset.
        # time.monotonic criterion prevents repeated resets between 3 and 4, and prevents resets 3h after restart if time is not realtime
        if time.localtime().tm_hour == 3 and time.monotonic() > 12000:
            microcontroller.reset()

    counter += 1
    time.sleep(0.0411) # average execution time is 8.9 ms, goal repetition time is 50 ms -> sleep 41.1 ms
    #print(f"{counter},{time.monotonic()}") # debug: timing check
