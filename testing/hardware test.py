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

from adafruit_mcp230xx.mcp23017 import MCP23017 # port expander
import adafruit_lis3dh # accelerometer
from adafruit_ltr329_ltr303 import LTR329 # light sensor
import adafruit_drv2605 # haptic driver
from adafruit_max1704x import MAX17048 # battery monitor

# HARDWARE SETUP
#
# set up 12V enable pin
enable_12V = digitalio.DigitalInOut(board.A3)
enable_12V.direction = digitalio.Direction.OUTPUT

# set up touch matrix
column_left = touchio.TouchIn(board.D9)
column_middle = touchio.TouchIn(board.D6)
column_right = touchio.TouchIn(board.D5)

row_1 = touchio.TouchIn(board.D10)
row_2 = touchio.TouchIn(board.D11)
row_3 = touchio.TouchIn(board.D12)
row_4 = touchio.TouchIn(board.D13)

touch_inputs = [row_1, row_2, row_3, row_4, column_left, column_middle, column_right]

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
haptic.sequence[0] = adafruit_drv2605.Effect(1) # effect 1: strong click, 27: short double click strong, 16: 1000 ms alert
haptic.play()

accelerometer = adafruit_lis3dh.LIS3DH_I2C(i2c, address=25)

light_sensor = LTR329(i2c)
light = light_sensor.visible_plus_ir_light - light_sensor.ir_light

battery_monitor = MAX17048(board.I2C())
logger.info(f"Battery voltage: {battery_monitor.cell_voltage:.2f} Volts")
logger.info(f"Battery percentage: {battery_monitor.cell_percent:.1f} %")

# get connected port expanders (adresses from 0x20 to 0x27, except the accelerometer is at 25)
port_expanders = []
for address in i2c_address_list:
    if (address >= 0x20 and address <= 0x24) or address == 0x26 or address == 0x27:
        mcp = MCP23017(i2c, address=address)
        port_expander.append(mcp)

# create compartment objects with IO ports
compartments = []
for expander in port_expanders:
    for compartment_per_expander in range(8):
        input = expander.get_pin(compartment_per_expander*2)
        output = expander.get_pin(compartment_per_expander*2+1)
        new_compartment = compartment.compartment(input, output)
        compartments.append(new_compartment)

# set up compartment LEDs # TODO: this may vary with connection scheme
for compartment_number, compartment in enumerate(compartments):
    compartment.LED = LED_connector_1[compartment_number]
