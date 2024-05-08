import time
import board
import touchio

import adafruit_drv2605 # haptic driver

import adafruit_mpr121

i2c = board.I2C()

haptic = adafruit_drv2605.DRV2605(i2c)
haptic.use_LRM()
haptic.sequence[0] = adafruit_drv2605.Effect(24) # effect 1: strong click, 27: short double click strong, 16: 1000 ms alert
#haptic.play()

mpr121 = adafruit_mpr121.MPR121(i2c, address=0x5B) # 0x5B, ADDR to VCC / close jumper

for x in range(12):
    print(x)
    print(mpr121.baseline_data(x))
    print(mpr121.filtered_data(x))
    print(mpr121.is_touched(x))
    print("----")


