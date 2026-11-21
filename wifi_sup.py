import asyncio
import network
#import time

# --- wifi (must be connected before the server starts) ---
async def wifi_connect(ssid, password, hostname):
    network.hostname(hostname)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
#   ssid += "ZZ"                         # make it fail, to test when getting time
    wlan.connect(ssid, password)
    # wait for connection (simple blocking version, fine at startup)
    for _ in range(10):
        if wlan.isconnected():
            break
        print(".", end="")
        await asyncio.sleep(1)
    print()
    print(wlan.ifconfig())

# async def blink():
#     # Stand-in for whatever else you want running during the connect
#     while True:
#         print("*", end="")
#         await asyncio.sleep_ms(1000)

async def main(my_ssid, my_password):
#   task = asyncio.create_task(blink())
    await wifi_connect(my_ssid, my_password, hostname="Boris")
#   task.cancel()
#   print("\nConnected:", wlan.ifconfig())

if __name__ == "__main__":
    import boris.secrets as secrets
    asyncio.run(main(secrets.WIFI_SSID, secrets.WIFI_PASSWORD))
   