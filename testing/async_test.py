import asyncio
import board
import digitalio
import time


async def request():  # Don't forget the async!
            print("Sent")
            await asyncio.sleep(1.5)  # Don't forget the await!
            print("Reply")


async def ui():  # Don't forget the async!
    led_task = asyncio.create_task(request())
    for x in range(10):
        print(x)
        await asyncio.sleep(0.1)
    print("Async: loop")
    await asyncio.gather(led_task)  # Don't forget the await!
    print("done")


asyncio.run(ui())
