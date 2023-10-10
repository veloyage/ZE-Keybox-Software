import time
import board
import touchio

import adafruit_drv2605 # haptic driver

i2c = board.I2C()

haptic = adafruit_drv2605.DRV2605(i2c)
haptic.use_LRM()
haptic.sequence[0] = adafruit_drv2605.Effect(24) # effect 1: strong click, 27: short double click strong, 16: 1000 ms alert
#haptic.play()

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

def print_raw():
    for touch in touch_inputs:
        print(touch.raw_value)
        time.sleep(0.01)

def cal_touch():
    for touch in touch_inputs:
        buffer = 0
        for _ in range(3):
            buffer += touch.raw_value
            time.sleep(0.01)
        touch.threshold = int(buffer/3) + 60

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

#print_raw()
pressed_count = 2
last_pressed = None
cal_touch()
buffer = [None] * pressed_count
i = 0

while True:
    buffer[i] = read_matrix() # read into buffer
    if len(set(buffer)) == 1: # if all buffer elements are the same
        if buffer[i] != last_pressed:
            last_pressed = buffer[i]
            if buffer[i] is not None:
                haptic.play()
                print (buffer[i])
    # handle index
    i += 1
    if i == pressed_count:
        i = 0

    time.sleep(0.05)
