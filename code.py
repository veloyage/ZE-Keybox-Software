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
# 1.0.0: initial production version, switched back to MQTT API
# 1.1.0: bugfixes, commented sections removed, CP9.0 compatible, HW revision variable added, made all I2C ICs "optional", visual modifications, added error/warning icons,
# 1.2.0: compartmentalized into ui.py, hardware.py, flink.py, networking.py


# TODO: add OTA updating, get time from adafruit to account for DST

# TODO: logging and versioning in separate .py files

# general imports
import time
import board
import digitalio

# import analogio
# import touchio
import pwmio
import busio
import neopixel
import supervisor
import sys
import microcontroller
import watchdog
import os
import storage

import wifi
import ssl

import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_io.adafruit_io import IO_MQTT  # , IO_HTTP
import adafruit_logging as logging

import compartment
import ui
import hardware
import flink
import networking

# version string
version = "1.2.0"

# enable watchdog to reset on error
microcontroller.watchdog.timeout = 30 #  seconds
microcontroller.watchdog.mode = watchdog.WatchDogMode.RAISE  # watchdog.WatchDogMode.RESET

#
# LOAD VARIABLES
#

SN = os.getenv("SN")
HW_revision = os.getenv("HW_revision")

compartment_number_saved = os.getenv("COMPARTMENT_NUMBER")
large_compartments = os.getenv("LARGE_COMPARTMENTS").split()

maintainance_code = os.getenv("MAINTAINANCE_CODE_PREFIX")

aio_username = os.getenv("ADAFRUIT_IO_USERNAME")
aio_key = os.getenv("ADAFRUIT_IO_KEY")
aio_feed_name = os.getenv("ADAFRUIT_IO_FEED")

tamper_alarm = os.getenv("TAMPER_ALARM")

#
# LOGGING SETUP
#

# Initialize log functionality
logger = logging.getLogger("schlüsselkasten_log")
logger.setLevel(logging.INFO)

def format_time():
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02}-{t.tm_mday:02}_{t.tm_hour:02}-{t.tm_min:02}-{t.tm_sec:02}"


# check if we have storage access and if so, open local logfile
try:
    storage.remount("/", False) # try to remount as writable, triggers exception if USB connected/visible
    if (time.localtime().tm_year < 2023):  # time incorrect, likely not set due to missing internet connection
        filename = "/logs/unknown_time.log"
    else:
        filename = f"/logs/{format_time()}.log"
    # check if there is enough space and delete old logs if necessary
    while True:
        fsstat = os.statvfs("/")
        free = fsstat[0] * fsstat[3]
        if free > 100000:  # ~100kb should be more than enough for one new logfile
            break
        else:   # if too little free space, delete oldest logfile
            logfilelist = os.listdir("/logs/")
            logfilelist.sort()
            os.remove("/logs/" + logfilelist[0])
    file_handler = logging.FileHandler(filename)
    logger.addHandler(file_handler)
    logger.info("Logging to local file started.")
    local_logging = True
except (OSError, RuntimeError) as e:  # When the filesystem is NOT writable, it's likely due to being connected to a computer -> log to console
    local_logging = False
    # if e.args[0] == 28: # filesystem full
    stream_handler = logging.StreamHandler()
    logger.addHandler(stream_handler)
    logger.info(e)  # send error as info, as it may occur regularly and is handled
    logger.info("Filesystem not writeable, logging to shell started.")

# process received command
def process_command(payload):
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
            ui.open_all(compartments)
        elif int(comp) > 0 and int(comp) <= len(compartments):
            compartments[comp].open()
        logger.info(f"Compartment open sent from MQTT broker: {comp}")
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
        except Exception as e:  # ignore exception, logging would trigger further exceptions
            print(e)
            pass

class DisplayLogHandler(logging.Handler):
    def emit(self, record):
        ui.log_labels[ui.next_label].text = record.msg
        ui.next_label += 1
        if ui.next_label == len(ui.log_labels):
            ui.next_label = 0

display_log = DisplayLogHandler()
logger.addHandler(display_log)

#
# NETWORKING SETUP
#
try:
    wifi_connected = networking.connect_wifi()
except Exception as e:
    wifi_connected = False
    logger.error(f"Error connecting to wifi: {e}")

try:
    ping = networking.get_ping()
except Exception as e:
    ping = None
    logger.error(f"Error during ping: {e}")

try:
    networking.get_time()
except Exception as e:
    logger.error(f"Error getting time: {e}")


# Callback function which will be called when a connection is established
def connected(client):
    client.subscribe(aio_feed_name + "command")

# Callback function which will be called when a message comes from a subscribed feed
def message(client, feed_id, payload):
    if feed_id == (aio_feed_name + "command"):
        process_command(payload)

# try to connect to MQTT broker and use it for logging
# Initialize a new MQTT Client object
mqtt_client = MQTT.MQTT(
    broker="io.adafruit.com",
    port=8883,
    is_ssl=True,
    username=aio_username,
    password=aio_key,
    socket_pool=networking.pool,
    ssl_context=ssl.create_default_context(),
    keep_alive = 120,
)
try:
    # Initialize an MQTT broker MQTT Client
    io = IO_MQTT(mqtt_client)
    # Set up the callback methods above
    io.on_connect = connected
    io.on_message = message
    io.connect()

    logger.addHandler(AIOLogHandler())
    logger.info("Logging to MQTT broker started.")
except Exception as e:
    logger.error(f"Error connecting to MQTT broker: {e}")

flink_log_handler = flink.FlinkLogHandler(logging.ERROR)
logger.addHandler(flink_log_handler)
logger.info("Logging to Flink started.")

# read processor UID and format it as hex-string (like it is in the boot_out.txt)
def hex_format(hex_in):
    string = ""
    for x in hex_in:
        string += f"{x:0{2}X}"
    return string

# update warning icons
if hardware.haptic is None or hardware.touch_sensor is None or hardware.accelerometer is None or hardware.light_sensor is None or hardware.battery_monitor is None:
    ui.maintainance_grid.hidden = False

#
# INFO MESSAGES
#
logger.info(f"Ziemann Engineering Schlüsselkasten {flink.ID}")
logger.info(f"Serial number {SN}, compartments: {compartment_number_saved}, large compartments: {large_compartments}")
logger.info(f"Versions: Software: {version}, hardware: {HW_revision}, CircuitPython: {sys.implementation.version[0]}.{sys.implementation.version[1]}.{sys.implementation.version[2]}")
logger.info(f"CPU ID: {hex_format(microcontroller.cpu.uid)}, temperature: {microcontroller.cpu.temperature:.2}°C")
logger.info(f"Reset reason: {str(microcontroller.cpu.reset_reason).split('.')[2]}, run reason: {str(supervisor.runtime.run_reason).split('.')[2]}")
if wifi_connected:
    logger.info(f"Wifi connected to {wifi.radio.ap_info.ssid}, RSSI: {wifi.radio.ap_info.rssi}.")
else:
    logger.warning("Wifi not connected.")
    ui.no_wifi_grid.hidden = False
logger.info(f"IP address: {wifi.radio.ipv4_address}, MAC: {hex_format(wifi.radio.mac_address)}")

if ping is not None:
    logger.info(f"Ping to google: {ping*1000} ms.")
else:
    logger.warning("Ping to google failed.")

status_code = flink.put_status(logger, time.monotonic(), SN, version, compartment_number_saved, large_compartments)
if status_code == 200:
    logger.info(f"Response from Flink: {status_code}.")
else:
    logger.warning(f"Response from Flink: {status_code}.")
    ui.no_flink_grid.hidden = False

if hardware.battery_monitor is not None:
    logger.info(f"Battery status: {hardware.battery_monitor.cell_voltage:.2f}V, {hardware.battery_monitor.cell_percent:.1f} %")

logger.info(f"{len(hardware.port_expanders)} compartment PCBs / rows detected.")
if len(hardware.port_expanders)*8 < compartment_number_saved:
    logger.error("Insufficient compartment PCBs detected.")
    ui.maintainance_grid.hidden = False


# calculate which spaces the large compartments take up.
# spaces = spots/port expander connections where individual compartments could be
# spaces formula: expander_index * 8 + compartment_per_expander + 1
# large_compartment_spaces = {}
for index in large_compartments:
    space = int(index)  # TODO?: only works for first large compartment
large_compartment_spaces = [space, space + 1, space + 8, space + 9]

# create compartment objects with IO ports, and a dict for all of them
compartments = {}
counter = 1
for index, expander in enumerate(hardware.port_expanders):
    for compartment_per_expander in range(8):
        space = index * 8 + compartment_per_expander + 1
        # large compartment handling
        if space in large_compartment_spaces:
            pos = large_compartment_spaces.index(space)
            if pos == 0:  # first space: create comp as normal
                pass  # skip to normal part
            elif pos == 1 or pos == 3:  # second, fourth space: add LED to first
                compartments[str(large_compartment_spaces[0])].LEDs.append(space - 1)
                continue
            elif pos == 2:  # third space: add IO to first, also LED
                compartments[str(large_compartment_spaces[0])].add_input(expander.get_pin(compartment_per_expander * 2))
                compartments[str(large_compartment_spaces[0])].add_output(expander.get_pin(compartment_per_expander * 2 + 1))
                compartments[str(large_compartment_spaces[0])].LEDs.append(space - 1)
                continue
        # normal compartments
        input_pin = expander.get_pin(compartment_per_expander * 2)
        output_pin = expander.get_pin(compartment_per_expander * 2 + 1)
        new_compartment = compartment.compartment(input_pin, output_pin)
        new_compartment.LEDs = [space - 1]
        new_compartment.LED_connector = hardware.LED_connector_1
        compartments[f"{counter}"] = new_compartment
        counter += 1


# check door of all compartments
def check_all():
    open_comps = []
    for index in range(len(compartments)):
        if compartments[str(index + 1)].get_inputs():
            open_comps.append(str(index + 1))
    return open_comps

# check if given code is in dict of valid codes, or a maintainance code. return compartment and status message
def check_code(code):
    if len(code) == 4:  # normal codes have 4 digits
        status_code, valid_codes = flink.get_codes(logger)  # get codes from Flink
        if status_code is not 200:
            logger.error(f"Error response from Flink when getting codes: {status_code}")
            return None, "error"
        if valid_codes is not None:
            for comp, comp_codes in valid_codes.items():
                if code in comp_codes:
                    return comp, "normal"
        return None, "invalid"
    elif len(code) == 8:  # maintainance codes have 8 digits
        if code[2:8] == maintainance_code:
            comp = int(code[0:2])
            return str(comp), "maintainance" # converted string to int and back to remove leading zeros
        else:
            return None, "invalid"
    else:
        return None, "invalid"


open_comps = check_all()
if len(open_comps) is not 0:
    logger.warning(f"Open compartments: {open_comps}")

logger.info("Startup complete.")

#
# Normal operation
#
last_pressed = None
code = ""
counter = 0

logger.removeHandler(display_log)  # stop logging to display

ui.main()  # configure main display with code and message

microcontroller.watchdog.feed()

hardware.LED_internal.fill((30, 30, 30))

# debug, execution time profiling
#last_time = time.monotonic()

while True:
    key = hardware.read_keypad()  # read into buffer
    if key != last_pressed:
        last_pressed = key
        if key is not None:
            hardware.haptic.play()
            if key is "✓":  # process input
                compartment_index, status = check_code(code)  # check if the code is in the list and return the compartment index if yes, None if not
                ui.process_compartment(compartments, compartment_index, logger)
                if status == "maintainance":
                    code = "maintainance"
                # Flink code log
                response = flink.post_code_log(logger, code, compartments, compartment_index)
                if (compartment_index is not None) and (compartment_index in compartments):
                    logger.info(f"Code '{code}' was entered, valid for compartment {compartment_index}, content status: {compartments[compartment_index].content_status}, door status: {compartments[compartment_index].door_status}.")
                    # after logging, set status back to unknown - we do not want to rely on the user answering correctly/truthfully. TODO?: this makes part of the status query code useless, remove?
                    # compartments[compartment_index].content_status = "unknown"
                elif compartment_index == "99":
                    logger.info("Maintainance code to open all compartments was entered.")
                else:
                    logger.info(f"Code '{code}' was entered, invalid")
                code = ""
                ui.code_label.text = code
            elif key is "x":  # clear input
                code = ""
                ui.code_label.text = code
            elif len(code) < 8:  # add number to code, ignore anything above 8 chars
                code = code + key
                if len(code) <= 4:
                    ui.code_label.text = code

    if hardware.accelerometer is not None and tamper_alarm == "on":
        x, y, z = hardware.accelerometer.acceleration  # in m/s2
        if abs(z) > 1:  # check accelerometer
            # TODO: message on screen
            hardware.LED_internal.fill((255, 0, 0))
            hardware.piezo.duty_cycle = int(0.5 * 65536)
        else:
            hardware.LED_internal.fill((0, 0, 0))
            hardware.piezo.duty_cycle = 0


    if counter % 101 == 0:  # runs roughly every 5 s
        microcontroller.watchdog.feed()  # reset the watchdog timer

        # check wifi, reconnect if necessary, update icon
        try:
            wifi_connected = networking.connect_wifi()
        except Exception as e:
            logger.error(f"Error reconnecting to wifi: {e}")
            wifi_connected = False
        ui.no_wifi_grid.hidden = wifi.radio.connected

        # check grid power connection
        ui.no_power_grid.hidden = hardware.supply_present.value

        if hardware.light_sensor is not None:
            try:
                light = hardware.light_sensor.visible_plus_ir_light - hardware.light_sensor.ir_light  # check brightness
                if light > 100:  # > 100 is relatively bright, > 1000 very bright
                    light = 100
                elif light < 0:
                    light = 0
                hardware.backlight.duty_cycle = int((0.1 + 0.9 * light / 100) * 65535)
                hardware.LED_internal.brightness = 0.1 + 0.9 * light / 100
                hardware.LED_connector_1.brightness = 0.1 + 0.9 * light / 100
                hardware.LED_connector_2.brightness = 0.1 + 0.9 * light / 100
            except Exception as e:
                logger.error(f"Error getting ambient brightness: {e}")

    if counter % 301 == 0:  # runs roughly every 15 s
        try:
            io.loop()  # get updates from MQTT broker, takes 1-2 s
        except Exception as e:
            logger.error(f"Error getting update from MQTT broker: {e}")
            try:
                io.reconnect()
            except Exception:
                logger.error(f"Error reconnecting to MQTT broker: {e}")

    if counter == 6001:  # runs roughly every 5 minutes
        counter = 0
        #logger.info(f"5 min task")
        # send status as keepalive
        status_code = flink.put_status(logger, time.monotonic(), SN, version, compartment_number_saved, large_compartments)
        if status_code is not 200:
            logger.warning(f"Response from Flink: {status_code}.")
            ui.no_flink_grid.hidden = False
        else:
            ui.no_flink_grid.hidden = True

        # check battery status
        if hardware.battery_monitor is not None:
            if hardware.battery_monitor.cell_voltage < 3.5:  # log if low battery
                logger.warning(f"Battery low: {battery_monitor.cell_voltage:.2f}V, {battery_monitor.cell_percent:.1f} %")
                ui.low_battery_grid.hidden = False
            else:
                ui.low_battery_grid.hidden = True

        # regularly reset device, eg at 3 AM. if time says 3 and runtime is > 3:20 h -> reset.
        # time.monotonic criterion prevents repeated resets between 3 and 4, and prevents resets 3h after restart if time is not realtime
        if time.localtime().tm_hour == 3 and time.monotonic() > 12000:
            microcontroller.reset()

    counter += 1
    time.sleep(0.045)  # goal repetition time is 50 ms
    #time_now = time.monotonic()
    #print(f"{time_now - last_time}") # debug: timing check
    #last_time = time_now

