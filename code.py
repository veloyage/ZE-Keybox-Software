# Ziemann Engineering Schlüsselkasten-Software
# main code file

version = "0.3"


# Changelog:
# 0.1: initial hardware test version, major TODOs: flink connection, key pickup/return logic, display UI, logging
# 0.2: added display, logging, initial readout and key logic
# 0.3: added keypad readout, more key logic, working compartment interface

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

import ipaddress
import ssl
import wifi
import socketpool
#import rtc
import adafruit_requests
import adafruit_ntp

import displayio
from adafruit_display_text import bitmap_label
from adafruit_bitmap_font import bitmap_font
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

import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_io.adafruit_io import IO_MQTT
# import adafruit_io
import adafruit_logging as logging

import compartment

#
# DISPLAY SETUP
#
displayio.release_displays()

spi = busio.SPI(board.SCK, MOSI=board.MOSI)

display_bus = displayio.FourWire(spi, command=board.TX, chip_select=board.A4, reset=board.RX, baudrate=40000000)
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

font_large = bitmap_font.load_font("/fonts/LiberationSans-Bold-140.pcf")
font_medium = bitmap_font.load_font("/fonts/LiberationSans-Bold-24.pcf")


#
# LOGGING SETUP
#

# if USB is not connected, we can write to the storage
if not supervisor.runtime.usb_connected:
    storage.remount("/", False)

# prepare for internet things
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# load variables from .toml file
ID = os.getenv("ID")
SN = os.getenv("SN")
compartment_number_saved = os.getenv("COMPARTMENT_NUMBER")
large_compartment = os.getenv("LARGE_COMPARTMENT")
wifi_ssid = os.getenv("CIRCUITPY_WIFI_SSID")

aio_username = os.getenv("ADAFRUIT_IO_USERNAME")
aio_key = os.getenv("ADAFRUIT_IO_KEY")

flink_URL = os.getenv("FLINK_URL")
flink_API_key = os.getenv("FLINK_API_KEY")

# try to get the time from the internet
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=2)
    rtc.RTC().datetime = ntp.datetime
except:
    online = False

# Initialize log functionality
logger = logging.getLogger("schlüsselkasten_log")
logger.setLevel(logging.INFO)

# prepare local file logging
if time.localtime().tm_year < 2023: # time incorrect, likely not set due to missing internet connection
    filename = "/logs/unknown_time.log"
else:
    t = time.localtime()
    filename = f"/logs/{t.tm_year}-{t.tm_mon:02}-{t.tm_mday:02}_{t.tm_hour:02}-{t.tm_min:02}-{t.tm_sec:02}.log"

# check if we have storage access and if so, open local logfile
try:
    file_handler = logging.FileHandler(filename)
    logger.addHandler(file_handler)
    logger.info("Logging to local file started.")
    local_logging = True
except OSError as e:  # When the filesystem is NOT writable, it's likely due to being connected to a computer -> log to console
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
    #logger.info(f"Internet available, ping to google: {ping * 1000} ms.")
    online = True
except Exception as e:
    logger.error(e)
    online = False

# if we have internet, connect to adafruit IO and use it for logging
if online:
    # Initialize a new MQTT Client object
    mqtt_client = MQTT.MQTT(
        broker="io.adafruit.com",
        port=8883,
        is_ssl=True,
        username=aio_username,
        password=aio_key,
        socket_pool=pool,
        ssl_context=ssl.create_default_context(),
    )
    try:
        # Initialize an Adafruit IO MQTT Client
        io = IO_MQTT(mqtt_client)
        io.connect()

        class AIOLogHandler(logging.Handler):
            def emit(self, record):
                io.publish("schlusselkasten-status", self.format(record))
        logger.addHandler(AIOLogHandler())
        logger.info("Logging to Adafruit IO started.")
    except Exception as e:
        logger.error(e)

    class FlinkLogHandler(logging.Handler):
        def emit(self, record):
            response = requests.post(f"{flink_URL}/{ID}/log", headers={"flink-api-key": flink_API_key}, json={"time": f"{record.created}", "level": f"{record.levelname}", "message": f"{record.msg}"})
    #logger.addHandler(FlinkLogHandler())
    #logger.info("Logging to Flink started.")

       # read processor UID and format it as hex-string (like it is in the boot_out.txt)
uid = microcontroller.cpu.uid
uid_string = ""
for x in uid:
    uid_string += f"{x:0{2}x}"

# info messages
logger.info(f"Ziemann Engineering Schlüsselkasten {ID}")
logger.info(f"Serial number {SN}, compartments: {compartment_number_saved}, large compartment: #{large_compartment}")

reset_reason = microcontroller.cpu.reset_reason
logger.info(f"CPU ID: {uid_string}, temperature: {microcontroller.cpu.temperature:.2}°C, last reset reason: {str(microcontroller.cpu.reset_reason).split('.')[2]}")
for network in wifi.radio.start_scanning_networks():
    if network.ssid == wifi_ssid:
        logger.info(f"Connected to {network.ssid}, RSSI: {network.rssi}")
        network_found = True
        break # print only first in case of multiple APs
wifi.radio.stop_scanning_networks()
if network_found is False:
    logger.info("Configured wifi network not found.")

if ping is not None:
   logger.info(f"IP address: {wifi.radio.ipv4_address}, ping to google: {ping * 1000} ms.")
else:
    logger.info(f"IP address: {wifi.radio.ipv4_address}, ping to google failed.")

# TODO: send status to flink

#
# HARDWARE SETUP
#
# set up 12V enable pin
enable_12V = digitalio.DigitalInOut(board.A3)
enable_12V.direction = digitalio.Direction.OUTPUT
enable_12V.value = False

# set up touch matrix
column_left = touchio.TouchIn(board.D9)
column_middle = touchio.TouchIn(board.D6)
column_right = touchio.TouchIn(board.D5)

row_1 = touchio.TouchIn(board.D10)
row_2 = touchio.TouchIn(board.D11)
row_3 = touchio.TouchIn(board.D12)
row_4 = touchio.TouchIn(board.D13)

touch_inputs = [row_1, row_2, row_3, row_4, column_left, column_middle, column_right]
touch_margin = [0] * 7

## LED config
LED_internal = neopixel.NeoPixel(board.A2, 6)
LED_connector_1 = neopixel.NeoPixel(board.A0, 32)
LED_connector_2 = neopixel.NeoPixel(board.A1, 1)


## I2C init
i2c = board.I2C()

while not i2c.try_lock():
    pass
i2c_address_list = i2c.scan()
i2c.unlock()

haptic = adafruit_drv2605.DRV2605(i2c)
haptic.use_LRM()
haptic.sequence[0] = adafruit_drv2605.Effect(24) # effect 1: strong click, 4: sharp click, 24: sharp tick,  27: short double click strong, 16: 1000 ms alert

accelerometer = adafruit_lis3dh.LIS3DH_I2C(i2c, address=25)

light_sensor = LTR329(i2c)
light = light_sensor.visible_plus_ir_light - light_sensor.ir_light

battery_monitor = MAX17048(i2c)
logger.info(f"Battery voltage: {battery_monitor.cell_voltage:.2f} V")
logger.info(f"Battery percentage: {battery_monitor.cell_percent:.1f} %")

# get connected port expanders (adresses from 0x20 to 0x27)
port_expanders = []
for address in i2c_address_list:
    if (address >= 0x20 and address <= 0x27):
        mcp = MCP23017(i2c, address=address)
        port_expanders.append(mcp)

# create compartment objects with IO ports
compartments = []
for expander in port_expanders:
    for compartment_per_expander in range(8):
        inputs = [expander.get_pin(compartment_per_expander*2)]
        outputs = [expander.get_pin(compartment_per_expander*2+1)]
        new_compartment = compartment.compartment(inputs, outputs)
        compartments.append(new_compartment)

# set up compartment LEDs # TODO: this may vary with connection scheme
for compartment_number, compartment in enumerate(compartments):
    compartment.LEDs = [LED_connector_1[compartment_number]]

logger.info(f"{len(port_expanders)} compartment PCBs / rows detected.")
if len(compartments) < compartment_number_saved:
    logger.error(f"Insufficient compartment PCBs detected")

def print_raw():
    for touch in touch_inputs:
        print(touch.raw_value)
        time.sleep(0.1)

def cal_touch():
    for touch in touch_inputs:
        time.sleep(0.1)
        touch.threshold = touch.raw_value + 70

def read_matrix():
    # read matrix
    pressed = None
    for index, touch in enumerate(touch_inputs):
        touch_margin[index] = touch.raw_value - touch.threshold

    column = touch_margin.index(max(touch_margin[4:]))
    row = touch_margin.index(max(touch_margin[:4]))

    if touch_inputs[column].value and touch_inputs[row].value:
        if column == 4:
            if row == 0:
                pressed = "1"
            elif row == 1:
                pressed = "4"
            elif row == 2:
                pressed = "7"
            elif row == 3:
                pressed = "x"
        if  column == 5:
            if row == 0:
                pressed = "2"
            elif row == 1:
                pressed = "5"
            elif row == 2:
                pressed = "8"
            elif row == 3:
                pressed = "0"
        if  column == 6:
            if row == 0:
                pressed = "3"
            elif row == 1:
                pressed = "6"
            elif row == 2:
                pressed = "9"
            elif row == 3:
                pressed = "✓" # testing unicode support
    return pressed

# debug: take console input
# def read_matrix():
#    return input()

welcome_text = "MAW Schlüsselkasten\n Buchungen auf Flink. \n  Bitte Code eingeben.  "
invalid_text = f"Code ungültig."

# Draw some label text
rect2 = Rect(0, 0, 320, 240, fill=0xFFFFFF)
default = displayio.Group()
default.append(rect2)
code_label = bitmap_label.Label(font_large, text="", color=0x005060, x=2, y=60, width=300)
default.append(code_label)
status_label = bitmap_label.Label(font_medium, text=welcome_text, color=0x005060, anchor_point=(0.5,0.5), anchored_position=(160,180))
default.append(status_label)
display.show(default)

valid_codes = [["1234", "1235"], ["2345", "2346"], ["3456", "3457"]]

LED_internal.fill((20,20,20))

# check if given code is in 2D list of valid codes
def check_code(code):
    for comp, comp_codes in enumerate(valid_codes):
        if code in comp_codes:
            return comp

# deal with compartment open/close logic
def process_compartment(compartment_index):
    if compartment_index is not None and compartment_index < len(compartments):
        # TODO: user feedback: success (LEDs, beep, haptic)
        compartments[compartment_index].set_LEDs((50,50,50))
        LED_internal.fill((0,50,0))
        status_label.text = f"Fach {compartment_index+1} wird geöffnet."
        time.sleep(1) # wait a second for the user to read
        status = compartments[compartment_index].open(0.5)
        if status == True: # successfully opened
            status_label.text = f"Bitte Inhalt entnehmen\nund Fach {compartment_index+1} schliessen."
            time.sleep(1) # wait a second for the user to read
        else: # not successfully opened, try again
            status_label.text = f"Bitte prüfen Sie ob \nFach {compartment_index+1} blockiert ist."
            time.sleep(5) # wait for the user to read and check
            status = compartments[compartment_index].open(2)
            if status == True: # successfully opened
                status_label.text = f"Bitte Inhalt entnehmen\nund Fach {compartment_index+1} schliessen."
            else:
                status_label.text = f"Fach öffnet sich nicht.\nBitte erneut versuchen,\noder Alternative buchen."
                time.sleep(8)
                # TODO: door could not be opened message
        counter = 3000
        while compartments[compartment_index].get_inputs() == True and counter > 0:
            time.sleep(0.1)
            counter -= 1
        if counter == 0:
            logger.warning(f"Door {compartment_index+1} not closed.")
        compartments[compartment_index].set_LEDs((0,0,0))
        LED_internal.fill((20,20,20))
        # TODO: code entered status
        status_label.text=welcome_text
    else:
        # TODO: user feedback: invalid (LEDs, beep, haptic)
        LED_internal.fill((60,0,0))
        status_label.text=invalid_text
        # TODO: code entered status
        time.sleep(3)
        LED_internal.fill((20,20,20))
        status_label.text=welcome_text

# TODO: get codes from flink
def get_codes():
    pass

#
# Normal operation
#
pressed_count = 2
last_pressed = None
cal_touch()
buffer = [None] * pressed_count
i = 0
code = ""

while True:
    buffer[i] = read_matrix() # read into buffer
    if len(set(buffer)) == 1: # if all buffer elements are the same
        if buffer[i] != last_pressed:
            last_pressed = buffer[i]
            if buffer[i] is not None:
                haptic.play()
                button = buffer[i]
                if button is "✓":
                    compartment_index = check_code(code) # check if the code is in the list and return the compartment index if yes, None if not
                    process_compartment(compartment_index)
                    code = ""
                    code_label.text = code
                elif button is "x":
                    code = ""
                    code_label.text = code
                else:
                    code = code + button
                    code_label.text = code
                    if len(code) == 1:
                        get_codes()
    # handle index
    i += 1
    if i == pressed_count:
        i = 0

    time.sleep(0.05)

