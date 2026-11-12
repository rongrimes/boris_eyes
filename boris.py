
import asyncio
import machine
import network
import utime

from boris.microdot import Microdot

app = Microdot()

# make global to turn off later.
led_onboard = None

ON  = 1
OFF = 0

# Time to run the eyes
# typically display period is 24 hours (in seconds)
# units = seconds
display_period = 24 * 60 * 60   # 24 hours - must be longer than display_time
display_time   = 5 * 60 * 60    # 5 hours
#test values
#display_period = 4 * 60  # 4 minutes
#display_time = 2 * 60     # 2 minutes

blink_step = 0.10
blink_pause = 0.75
eyes_sleep = 8.0
eyes_awake = 8.0
blinks = 4

# Global settings - changed only by the microdot web interface.
# Hence (hoping) no critical update zone to set up.

settings = {'eye_brightness': 50, 'eye_mode': 'idle',
            'Display cycle': display_period,   # Full period of Boris "wake/doze time" and
                                               # "doze/wake" time
            'Display period': display_period,  # Time for "wake/doze" time
            'Blink step': blink_step,          # Time between steps to open & close an eye
            'Blink pause': blink_pause,        # Time the eye is opn or closed during a blink
            'Eyes sleep': eyes_sleep,          # Time the eyes are asleep/wake 
            'Eyes awake': eyes_awake,
            'Blinks': blinks,                  # Number of blinks/wakes during a wake/doze period 
            }



# pin assignments
left_p = ["GP2", "GP1", "GP0"]
rite_p = ["GP28", "GP27", "GP26"]
# Note: Pin 1 is: "GP1", not "GP01"

# Hold list for the pin objects
left_e = [None, None, None]
rite_e = [None, None, None]

#systems_go = asyncio.Event()  # cleared by default

night_also = True

#--------------------------------------------------------------------------
# Web communications

#@app.route('/')
# async def index(request):
#     return 'Hello, world!'

@app.get('/')
async def index(request):
#   settings = {'eye_brightness': 50, 'eye_mode': 'idle'}

    return (
        '<h3>Spider</h3>'
        f"<p>{settings}</p>"
        '<form method="post" action="/set/eye_mode/blink"><button>Blink</button></form>'
        '<form method="post" action="/set/eye_mode/idle"><button>Idle</button></form>',
        200, {'Content-Type': 'text/html'}
    )

@app.post('/set/<name>/<value>')
async def set_value(request, name, value):
    if name not in settings:
        return 'unknown setting', 404
    try:
        settings[name] = type(settings[name])(value)
    except ValueError:
        return 'bad value', 400
    return 'ok'

#--------------------------------------------------------------------------

async def clock():
    global night_also
    while True:
#       systems_go.set()    # start the clock
        night_also = True
        await asyncio.sleep(display_time)
#       systems_go.clear()  # turn off the cloxk
        night_also = False
        await asyncio.sleep(display_period - display_time)

async def heart_beat(led_onboard):
    while True:
#   Can't catch the keyboard interrupt in this or other tasks - feature of micropython     try:
        led_onboard.toggle()
        await asyncio.sleep(1)

async def boris_eyes():
#   blink_step = 0.10
#   blink_pause = 0.75
#   eyes_sleep = 8.0
#   eyes_awake = 8.0
#   blinks = 4
#   blinks = 2
    
    def opcl_eye(eye, on_off):
        for i in range(3):
            p =eye[i]
            p.value(on_off)
    
    async def toggle_eyes(left_e, rite_e, seq):
        for i in seq:
            p =left_e[i]
            p.toggle()
            p =rite_e[i]
            p.toggle()
            if i == seq[-1]: # don't wait on last iteration
                break
            await asyncio.sleep(blink_step)
        
    async def blink_eyes_clos(left_e, rite_e):
        await toggle_eyes(left_e, rite_e, [2,1,0])  # off
        await asyncio.sleep(blink_pause)
        await toggle_eyes(left_e, rite_e, [0,1,2])  # on

    async def blink_eyes_open(left_e, rite_e):
        await toggle_eyes(left_e, rite_e, [0,1,2])  # on
        await asyncio.sleep(blink_pause)
        await toggle_eyes(left_e, rite_e, [2,1,0])  # off

# set to start
    opcl_eye(left_e, OFF)
    opcl_eye(rite_e, OFF)

    while True:
#       assert Eyes off

#       await systems_go.wait()   # ensure we can continue

        if night_also:
            await toggle_eyes(left_e, rite_e, [0,1,2])  # on               
            for _ in range(blinks):
                await asyncio.sleep(eyes_sleep)
                await blink_eyes_clos(left_e, rite_e)
            await asyncio.sleep(eyes_awake)
            await toggle_eyes(left_e, rite_e, [2,1,0])  # off

        for _ in range(blinks):
            await asyncio.sleep(eyes_awake)
            await blink_eyes_open(left_e, rite_e)
        await asyncio.sleep(eyes_sleep)

async def main():
#   setup tasks
#   await asyncio.gather(heart_beat(led_onboard), boris_eyes(), clock())
    await asyncio.gather(
        heart_beat(led_onboard),
        boris_eyes(),
        clock(),
        app.start_server(port=80),
    )

# --- wifi (must be connected before the server starts) ---
def wifi_connect(ssid, password, hostname):
    network.hostname(hostname)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    # wait for connection (simple blocking version, fine at startup)
    import time
    for _ in range(20):
        if wlan.isconnected():
            break
        print(".", end="")
        time.sleep(1)
    print()
    print(wlan.ifconfig())

# ---------------------------------------------------------------------
# Start here

import boris.secrets as secrets
wifi_connect(ssid=secrets.WIFI_SSID, password=secrets.WIFI_PASSWORD,
             hostname='Boris')

#if __name__ == "__main__":
#   Initialize global pins
led_onboard = machine.Pin("LED", machine.Pin.OUT)

for i in range(3): 
    left_e[i] = machine.Pin(left_p[i], machine.Pin.OUT)
    rite_e[i] = machine.Pin(rite_p[i], machine.Pin.OUT)

#   run tasks
try:
    asyncio.run(main())

except KeyboardInterrupt:
#       turn off lights
    led_onboard.off()
    for i in range(3): 
        left_e[i].off()
        rite_e[i].off()

    print("Bye bye from Boris!")
