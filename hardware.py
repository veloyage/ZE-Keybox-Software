#
# Schlüsselkasten Hardware SETUP
#

import busio
import board
import pwmio
import digitalio
import neopixel

from adafruit_mcp230xx.mcp23017 import MCP23017 # port expander
import adafruit_lis3dh # accelerometer
from adafruit_ltr329_ltr303 import LTR329 # light sensor
import adafruit_drv2605 # haptic driver
from adafruit_max1704x import MAX17048 # battery monitor
import adafruit_mpr121 # touch sensor

# version string
version = "1.2.1"

backlight = pwmio.PWMOut(board.A5, frequency=1000, duty_cycle=int(1 * 65535))

# set up 12V enable pin
enable_12V = digitalio.DigitalInOut(board.A3)
enable_12V.direction = digitalio.Direction.OUTPUT
enable_12V.value = False

# set up supply detection pin
supply_present = digitalio.DigitalInOut(board.D10)
supply_present.direction = digitalio.Direction.INPUT

## LED config
LED_internal = neopixel.NeoPixel(board.A2, 6)
LED_connector_1 = neopixel.NeoPixel(board.A1, 32)
LED_connector_2 = neopixel.NeoPixel(board.A0, 32)

# piezo buzzer
piezo = pwmio.PWMOut(board.MISO, frequency=1000, duty_cycle=0)

# bus init
i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)

try:
    haptic = adafruit_drv2605.DRV2605(i2c) # 0x5A
    haptic.use_LRM()
    haptic.sequence[0] = adafruit_drv2605.Effect(1) # effect 1: strong click, 4: sharp click, 24: sharp tick,  27: short double click strong, 16: 1000 ms alert
except Exception as e:
    haptic = None
    #TODO: logger.error(f"Error setting up haptic engine: {e}")

try:
    accelerometer = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x19)
except Exception as e:
    accelerometer = None
    #TODO: logger.error(f"Error setting up accelerometer: {e}")

try:
    light_sensor = LTR329(i2c) # 0x29
except Exception as e:
    light_sensor = None
    #TODO: logger.error(f"Error setting up brightness sensor: {e}")

try: # some boards have a different or no battery monitor, deal with it
    battery_monitor = MAX17048(i2c) # 0x36
except Exception:
    battery_monitor = None
    #TODO: logger.error(f"Error setting up battery monitor: {e}")

try:
    touch_sensor = adafruit_mpr121.MPR121(i2c, address=0x5B) # 0x5B, ADDR to VCC / close jumper
except Exception as e:
    touch_sensor = None
    #TODO: logger.error(f"Error setting up touch sensor: {e}")

# also on the bus at 0x38: touch screen controller FT6206

# get connected port expanders (adresses from 0x20 to 0x27, prototype PCBs: 0x24 to 0x27)
port_expanders = []
for addr in range(0x20, 0x28):
    try:
        port_expanders.append(MCP23017(i2c, address=addr))
    except: # ValueError if device does not exist, ignore
        pass


keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "x", "0", "✓"]
# read touch pads with MPR121
def read_keypad():
    touched_list = []
    if touch_sensor is not None:
        touched = touch_sensor.touched()
        for i in range(12):
            if touched & (1 << i):
                touched_list.append(i)
        if len(touched_list) == 1:  # only if exactly one button is pressed
            return keys[touched_list[0]]  # assumes pads are wired sequentially
        else:
            return None
    else:
        return None
