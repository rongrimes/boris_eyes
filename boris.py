
import asyncio
import machine
import network
import ntptime
import time

ET_OFFSET = -5   # EDT; use -4
#                # EST; use -5

from boris.microdot import Microdot

IP_PORT = 5000
app = Microdot()

# make global to turn off later.
led_onboard = None

ON  = 1
OFF = 0

# Time to run the eyes in boris awake mode a,d boris asleep mode
# typically display period is 24 hours (in minutes)
# units = minutes
boris_awake_time  = 5 * 60   # (mins) 24 hours
boris_asleep_time = 19 * 60    # (mins) 5 hours
#test values
#boris_awake_time = 4  # 4 minutes
#boris_awake_time = 2     # 2 minutes

blink_step = 0.10
blink_pause = 0.8
betw_blinks_awakes = 5
blinks = 4

# Global settings - changed only by the microdot web interface.
# Hence (hoping) no critical update zone to set up.


# (key, label, type, min, max, step)
FIELDS = [
    ('boris_awake_time',  'Boris awake time (mins)',   int,   1,   5 * 60, 1),
    ('boris_asleep_time', 'Boris asleep time (mins)',  int,   0,  19 * 60, 1),
    ('blinks',         'Blink-alerts/cycle',        int,   0,  10,  1),
    ('betw_blinks_awakes',     'Betwn blinks-alerts (s)',    int,   0,  20, 1),
    ('blink_step',     'Blink/Alert step (s)',    float, 0,  1.0,   0.1),
    ('blink_pause',    'Blink/Alert wait (s)',   float, 0,  1.0,   0.1),
]
FIELD = {f[0]: f for f in FIELDS}

# start from your existing values (float() makes sure the real ones stay real)
settings = {
    'boris_awake_time':      boris_awake_time,
    'boris_asleep_time':     boris_asleep_time,
    'blink_step':            float(blink_step),
    'blink_pause':           float(blink_pause),
    'betw_blinks_awakes':    betw_blinks_awakes,
    'blinks':                blinks,
}

#--------------------------------------------------------------------------
# Web communications
#function show(k, v) { document.getElementById('v_' + k).textContent = v; }

HEAD = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boris</title></head><body><h3>Boris</h3>"""

TAIL = """<div style="width:400px;">
<p>
<b>Awake:</b> Eyes are on, with brief blinks.<br/>
<b>Asleep:</b> Eyes are off, with brief alerts (open).<br/>
<b>Cycle:</b> One session of Boris Awake or Asleep.<p/>
<b>Boris awake time:</b>&nbsp; Period of equal Awake and Asleep times.<br/>
<b>Boris asleep time:</b> Period of Asleep cycle only.<br/>
<p>
The goal for Awake/Asleep time is to span 24 hours. Typically, 5 hours for
Awake time (after turn on), followed by 19 hours of Asleep time, where the eyes only
come on briefly ("alert"). The spirit is to save power and to be not annoying during
non-peak times. 
</p>
</div>
<script>
function show(k, v) { document.getElementById('v_' + k).textContent = v; }
function setv(k, v) {
  fetch('/set/' + k + '/' + v, {method: 'POST'})
    .then(r => r.text())
    .then(t => { if (t !== 'ok') alert(k + ': ' + t); });
}
</script></body></html>"""

def build_page():
    rows = ''
    for key, label, typ, lo, hi, step in FIELDS:
        v = settings[key]
        if typ is float:
            ctl = ('<input type="range" min="%s" max="%s" step="%s" value="%s" '
                   'style="width:200px" oninput="show(\'%s\',this.value)" '
                   'onchange="setv(\'%s\',this.value)">') % (lo, hi, step, v, key, key)
            rows += '<p><span style="display: inline-block; width:150px;">%s:</span> <b id="v_%s">%s</b>&nbsp;&nbsp;%s</p>' \
                    % (label, key, v, ctl)
        else:
            ctl = ('<input type="number" min="%s" max="%s" step="%s" value="%s" ' + \
                   'style="text-align: right;" ' + \
                    'onchange="setv(\'%s\',this.value)">') % (lo, hi, step, v, key)
            rows += '<p><span style="display: inline-block; width:200px;">%s:</span> %s</p>' \
                    % (label, ctl)
#       rows += '<p>%s: <b id="v_%s">%s</b><br>%s</p>' % (label, key, v, ctl)
    return HEAD + rows + TAIL

#@app.route('/')
# async def index(request):
#     return 'Hello, world!'

@app.get('/')
async def index(request):
    return build_page(), 200, {'Content-Type': 'text/html'}

@app.post('/set/<name>/<value>')
async def set_value(request, name, value):
    if name not in FIELD:
        return 'unknown setting', 404
    _, _, typ, lo, hi, step = FIELD[name]
    try:
        new = typ(value)
    except ValueError:
        print(f'bad value: {value} -> 400')
        return 'bad value', 400
    if typ is float:
        new = round(new, 1)          # keeps 0.30000000000000004 out of the settings
    if not lo <= new <= hi:
        return 'out of range', 400
    settings[name] = new
    print(f"name: {name}  // value: {new}")
    return 'ok'


# pin assignments
left_p = ["GP2", "GP1", "GP0"]
rite_p = ["GP28", "GP27", "GP26"]
# Note: Pin 1 is: "GP1", not "GP01"

# Hold list for the pin objects
left_e = [None, None, None]
rite_e = [None, None, None]

# start off with boris in awake mode
boris_awake = True

#--------------------------------------------------------------------------

async def clock():
    ''' clock() simply toggles the boris_awake variable, which is used to control
        which mode the eyes are in. '''
    global boris_awake
    while True:
        boris_awake = True
        await asyncio.sleep(settings['boris_awake_time'] * 60)
        boris_awake = False
        await asyncio.sleep(settings['boris_asleep_time'] * 60)  # units are mins

async def heart_beat(led_onboard):
    ''' simply flashes the pi pico status light to show the board/program are alive'''
    while True:
#   Can't catch the keyboard interrupt in this or other tasks - feature of micropython     try:
        led_onboard.toggle()
        await asyncio.sleep(1)

async def boris_eyes():   
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
            await asyncio.sleep(settings['blink_step'])
        
    async def blink_eyes_clos(left_e, rite_e):
        await toggle_eyes(left_e, rite_e, [2,1,0])  # off
        await asyncio.sleep(settings['blink_pause'])
        await toggle_eyes(left_e, rite_e, [0,1,2])  # on

    async def blink_eyes_open(left_e, rite_e):
        await toggle_eyes(left_e, rite_e, [0,1,2])  # on
        await asyncio.sleep(settings['blink_pause'])
        await toggle_eyes(left_e, rite_e, [2,1,0])  # off

# set to start
    opcl_eye(left_e, OFF)
    opcl_eye(rite_e, OFF)

    while True:
#       assert Eyes off
        if boris_awake:
            # turn eyes on
            await toggle_eyes(left_e, rite_e, [0,1,2]) #on
            # then blink them
            for _ in range(settings['blinks']):
                await asyncio.sleep(settings['betw_blinks_awakes'])
                await blink_eyes_clos(left_e, rite_e)
            await asyncio.sleep(settings['betw_blinks_awakes'])
            await toggle_eyes(left_e, rite_e, [2,1,0])  # off

#       When boris is not awake... 11pm to 7am for example
#       assert Eyes off
        for _ in range(settings['blinks']):
            await asyncio.sleep(settings['betw_blinks_awakes'])
            await blink_eyes_open(left_e, rite_e)
        await asyncio.sleep(settings['betw_blinks_awakes'])

async def main():
#   setup tasks
#   await asyncio.gather(heart_beat(led_onboard), boris_eyes(), clock())
    await asyncio.gather(
        heart_beat(led_onboard),
        boris_eyes(),
        clock(),
        app.start_server(port=IP_PORT),
    )

# --- wifi (must be connected before the server starts) ---
def wifi_connect(ssid, password, hostname):
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
        time.sleep(1)
    print()
    print(wlan.ifconfig())

def get_time():
    ntptime.timeout = 2
    try:
        ntptime.settime()          # sets the RTC to UTC
    except OSError:
        print("OSError. time retrieval abandoned")
        return 0
    offset = ET_OFFSET * 3600   # EDT; use -4
                                # EST; use -5
    t = time.localtime(time.time() + offset)
    return t

# ---------------------------------------------------------------------
# Start here

import boris.secrets as secrets
wifi_connect(ssid=secrets.WIFI_SSID, password=secrets.WIFI_PASSWORD,
             hostname='Boris')

boris_time = get_time()
print(f"Boris time: {boris_time}")

# We'll use the time in a later update when we set hours for the Awake/Asleep activities

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
