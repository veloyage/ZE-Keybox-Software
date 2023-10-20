
import time

import board

import ssl
import wifi
import socketpool
import adafruit_requests
import os



# internet things


pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

flink_URL = os.getenv("FLINK_URL")
flink_API_key = os.getenv("FLINK_API_KEY")
ID = os.getenv("ID")

#print(f"Fetching and parsing json from {flink_URL}/{ID}/codes")
#response = requests.get(f"{flink_URL}/{ID}/codes", headers={"flink-api-key": flink_API_key})
#print(response.json())

print(f"Putting status to {flink_URL}/{ID}/status?compartment=13")
response = requests.put(f"{flink_URL}/{ID}/status?compartment=13", headers={"flink-api-key": flink_API_key}, json={"booking_status": "available", "content_status": "filled", "door_status": "open", "size": "small"})
print(response.status_code)

print(f"Logging to {flink_URL}/{ID}/log")
response = requests.post(f"{flink_URL}/{ID}/log", headers={"flink-api-key": flink_API_key}, json={"time": "134.456", "level": "INFO", "message": "fake log message"})
print(response.status_code)
