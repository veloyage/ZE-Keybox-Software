import os
import time
import adafruit_logging as logging

import networking

flink_timeout = 5

ID = os.getenv("ID")
flink_URL = os.getenv("FLINK_URL")
flink_API_key = os.getenv("FLINK_API_KEY")

def format_time():
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02}-{t.tm_mday:02}_{t.tm_hour:02}-{t.tm_min:02}-{t.tm_sec:02}"

# send status to Flink
def put_status(logger, uptime, SN, version, comps, large_comps):
    try:
        response = networking.requests.put(
            f"{flink_URL}/{ID}/status",
            headers={"Authorization": flink_API_key},
            json={
                "time": format_time(),
                "uptime": f"{uptime}",
                "serial": f"{SN}",
                "version": f"{version}",
                "compartments": f"{comps}",
                "large_compartments": f"{large_comps}",
            },
            timeout=flink_timeout,
        )
        return response.status_code
    except Exception as e:
        logger.error(f"Error putting status: {e}")
        return e


# get codes from Flink
def get_codes(logger):
    try:
        response = networking.requests.get(
            f"{flink_URL}/{ID}/codes",
            headers={"Authorization": flink_API_key},
            timeout=flink_timeout,
        )
        return response.status_code, response.json()
    except Exception as e:
        logger.error(f"Error getting codes: {e}")
        return e, None


def post_code_log(logger, code, compartments, compartment_index):
    if (compartment_index is not None) and (compartment_index in compartments):
        content = compartments[compartment_index].content_status
        door = compartments[compartment_index].door_status
    else:
        content = None
        door = None
    try:
        response = networking.requests.post(
            f"{flink_URL}/{ID}/code_log",
            headers={"Authorization": flink_API_key},
            json={
                "time": format_time(),
                "code_entered": f"{code}",
                "compartment": f"{compartment_index}",
                "content": content,
                "door": door,
            },
            timeout=flink_timeout,
        )
        return response.status_code
    except Exception as e:
        logger.error(f"Error posting code log: {e}")
        return e


class FlinkLogHandler(logging.Handler):
    def emit(self, record):
        try:
            response = networking.requests.post(
                f"{flink_URL}/{ID}/error_log",
                headers={"Authorization": flink_API_key},
                json={
                    "time": format_time(),
                    "uptime": f"{record.created}",
                    "level": f"{record.levelname}",
                    "message": f"{record.msg}",
                },
                timeout=flink_timeout,
            )
        except Exception:  # ignore, otherwise we will get another error while logging
            pass
