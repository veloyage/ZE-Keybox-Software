# Ziemann Engineering Schlüsselkasten-Software
# compartment class, each compartment gets an object

import time
import digitalio

maximum_on_time = 5 # set maximum lock on time
check_time = 0.5 # time to sleep between door checks

class compartment():
    def __init__(self, input_pins, output_pins):
        self.type = "small" # small, big (only one, set manually)
        self.door_status = "closed" # closed, open, error (e.g. detected open without command)
        self.status_inputs = input_pins
        self.lock_outputs = output_pins
        self.LEDs = None

        # Setup output
        for output in self.lock_outputs:
            output.direction = digitalio.Direction.OUTPUT

        # Setup input with a pull-up resistor enabled
        for input in self.status_inputs:
            input.direction = digitalio.Direction.INPUT
            input.pull = digitalio.Pull.UP

    def set_LEDs(self, color):
        for LED in self.LEDs:
            LED = color

    def get_inputs(self):
        open = True
        for input in self.status_inputs:
            if input.value == False: # count inputs which are low -> switch is pressed, door is closed (considered closed if one switch is pressed)
                open = False
        return open  # if sum > 0, door is closed

    def set_outputs(self, status):
        for output in self.lock_outputs:
            output.value = status

    def open(self, on_time=1):
        if on_time > maximum_on_time:
            on_time = maximum_on_time
        counter = on_time / check_time
        self.set_outputs(True)
        while self.get_inputs() == False and counter > 0:
            time.sleep(check_time)# TODO: non-blocking?
            counter -= 1
        self.set_outputs(False)
        return self.get_inputs()
