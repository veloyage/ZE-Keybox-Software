import os
import ssl
import wifi
import socketpool
import adafruit_requests
import ipaddress
import rtc
import adafruit_ntp

pool = socketpool.SocketPool(wifi.radio)

requests = adafruit_requests.Session(pool, ssl.create_default_context())

wifi_ssid = os.getenv("CIRCUITPY_WIFI_SSID")
wifi_pw = os.getenv("CIRCUITPY_WIFI_PASSWORD")

# connects to wifi if currently not connected
def connect_wifi():
    if not wifi.radio.connected:
        wifi.radio.connect(wifi_ssid, wifi_pw)
    return wifi.radio.connected

# gets time (UTC) from NTP
def get_time():
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)
    rtc.RTC().datetime = ntp.datetime

# ping to check connectivity
def get_ping():
    ping_ip = ipaddress.IPv4Address("8.8.8.8") # ping google dns
    ping = wifi.radio.ping(ip=ping_ip)
    return ping
