
import asyncio
import machine
import ntptime
import time

ET_OFFSET = -5   # EDT; use -4
#                # EST; use -5

from boris.wifi_sup import wifi_connect
from boris.microdot import Microdot, send_file

IP_PORT = 5000
app = Microdot()

# make global to turn off later.
led_onboard = None

ON  = 1
OFF = 0

# Initial times to run the eyes in boris awake mode and boris asleep mode.
# Typically display period is 24 hours (in minutes)
# units = minutes
boris_awake_time  = 5 * 60   # (mins) 24 hours
boris_asleep_time = 19 * 60    # (mins) 5 hours

# start off with boris in awake mode
boris_awake = True

# Counting mins in clock - global to display/export them
awk_mins  = 0
aslp_mins = 0

blink_step = 0.10
blink_pause = 0.8
betw_blinks_awakes = 5
blinks = 4

# Global settings - changed only by the microdot web interface.
# Hence (hoping) no critical update zone to set up.

# (key, label, type, min, max, step)

FIELDS_floats  = [
    ('blink_step',        'Blink/Alert step (s)',    float, 0,  1.0,   0.1),
    ('blink_pause',       'Blink/Alert wait (s)',    float, 0,  2.0,   0.1),
]

FIELDS_intvars = [
    ('boris_awake_time',  'Boris awake time (mins)',   int,   1,  1440, 1),
    ('boris_asleep_time', 'Boris asleep time (mins)',  int,   0,  1440, 1),
    ('blinks',            'Blink-alerts/cycle',        int,   0,  10,   1),
    ('betw_blinks_awakes','Betwn blinks-alerts (s)',   int,   0,  20,   1),
]
FIELDS_cntrs = [
    ('awk_mins',  'Awake  mins cntr', "awk"), 
    ('aslp_mins', 'Asleep mins cntr', "aslp")
]

# Collect the fields cming back from a web browser to validate against.
FIELD = {f[0]: f for f in FIELDS_floats}  | \
        {f[0]: f for f in FIELDS_intvars}

# start from your existing values (float() makes sure the real ones stay real)
settings = {
    'boris_awake_time':      boris_awake_time,
    'boris_asleep_time':     boris_asleep_time,
    'blink_step':            float(blink_step),
    'blink_pause':           float(blink_pause),
    'betw_blinks_awakes':    betw_blinks_awakes,
    'blinks':                blinks,
    'awk_mins':              awk_mins,
    'aslp_mins':             aslp_mins,   
}

#--------------------------------------------------------------------------
# Web communications
#function show(k, v) { document.getElementById('v_' + k).textContent = v; }

HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boris</title>
</head><body><h3>Boris</h3>"""

TAIL = """<div style="width:400px;">
<p>
<b>Awake:</b> Eyes are on, with brief blinks.<br/>
<b>Asleep:</b> Eyes are off, with brief alerts (open).</p>
<p>
<b>Boris awake time:</b>&nbsp; Full period of alternating Awake and<br/>
&nbsp;&nbsp;&nbsp;Asleep cycles.<br/>
<b>Boris asleep time:</b> Full period of Asleep cycle only.<br/>
<b>Cycle:</b> One session of Boris Awake or Asleep.</p>
<p>
The goal for Awake/Asleep time is to span 24 hours. Typically, 5 hours for
Awake time (after turn on), followed by 19 hours of Asleep time, where the eyes only
come on briefly ("alert"). The spirit is to save power and to be not annoying during
non-peak times. 
</p>
</div>
<script>
let timer = null;
let failures = 0;
const MAX_FAILURES = 3;

function show(k, v) { document.getElementById('v_' + k).textContent = v; }
function setv(k, v) {
  fetch('/set/' + k + '/' + v, {method: 'POST'})
    .then(r => r.text())
    .then(t => { if (t !== 'ok') alert(k + ': ' + t); });
}
    async function update() {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 3000);   // give up on a hung request after 3 s
        const r = await fetch("/status", { cache: "no-store", signal: ctrl.signal } );
        clearTimeout(t);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const d = await r.json();
 
        failures = 0;
        document.getElementById("state").textContent = d.state ? "awake" : "asleep"; 
        document.getElementById("awk").textContent = d.awk;
        document.getElementById("aslp").textContent = d.aslp;
      } catch (e) {
        failures++;
        console.error("update failed:", e);
        if (failures >= MAX_FAILURES) {
          clearInterval(timer);
          document.getElementById("state").textContent = "OFFLINE (reload to retry)";
        }
      }
    }

    update();                    // fill in values immediately on load
    timer = setInterval(update, 10000);  // then every 10 seconds
</script></body></html>"""

def build_page():
    rows = ''
    for key, label, typ, lo, hi, step in FIELDS_intvars:
        v = settings[key]
        ctl = ('<input type="number" min="%s" max="%s" step="%s" value="%s" ' + \
               'style="text-align: right;" ' + \
                'onchange="setv(\'%s\',this.value)">') % (lo, hi, step, v, key)
        rows += '<p><span style="display: inline-block; width:200px;">%s:</span> %s</p>' \
                % (label, ctl)

    for key, label, typ, lo, hi, step in FIELDS_floats:
        v = settings[key]
        ctl = ('<input type="range" min="%s" max="%s" step="%s" value="%s" '
               'style="width:150px" oninput="show(\'%s\',this.value)" '
               'onchange="setv(\'%s\',this.value)">') % (lo, hi, step, v, key, key)
        rows += '<p><span style="display: inline-block; width:200px;">%s: &nbsp;<b id="v_%s">%s</b></span>%s</p>' \
                % (label, key, v, ctl)

    rows += '<p><span style="display: inline-block; width:200px;">Boris state:</span> ' + \
            f'<b><span id="state">{boris_awake}</span></b></p>'

    for key, label, id_key in FIELDS_cntrs:
        v = settings[key]
        rows += f'<p><span style="display: inline-block; width:200px;">{label}:</span> ' + \
                f'<b><span id="{id_key}">-</span></b></p>'

    return HEAD + rows + TAIL

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
    print(f"{name}  // value: {new}")
    return 'ok'

@app.route("/status")
def status(request):
    return {
        'state': boris_awake,
        'awk': settings['awk_mins'],
        'aslp': settings['aslp_mins'],
    }, 200, {'Cache-Control': 'no-store'}

@app.route('/')
def index(request):
    return send_file('index.html')

# pin assignments
left_p = ["GP2", "GP1", "GP0"]
rite_p = ["GP28", "GP27", "GP26"]
# Note: Pin 1 is: "GP1", not "GP01"

# Hold list for the pin objects
left_e = [None, None, None]
rite_e = [None, None, None]

#--------------------------------------------------------------------------

async def clock():
    ''' clock() simply toggles the boris_awake variable, which is used to control
        which mode the eyes are in. '''
    global boris_awake
    global settings
    
    # Note: Can't use a for loop here - we need to check the exit criteria against
    #       a dynamic limit, and a for loop only ends with a static limit 

    while True:
        boris_awake = True
        settings['awk_mins'] = 0
        while True:
            if settings['awk_mins'] >= settings['boris_awake_time']:  # this may happen if the value is reduced globally
                settings['awk_mins'] = 0
                break
            await asyncio.sleep(60)
            settings['awk_mins'] += 1
            
        boris_awake = False
        settings['aslp_mins'] = 0
#       for aslp_mins in range(settings['boris_asleep_time']):
        while True:
            if settings['aslp_mins'] >= settings['boris_asleep_time']:  # this may happen if the value is reduced globally
                settings['aslp_mins'] = 0
                break
            await asyncio.sleep(60)
            settings['aslp_mins'] += 1

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

# def get_time():
#     ntptime.timeout = 2
#     try:
#         ntptime.settime()          # sets the RTC to UTC
#     except OSError:
#         print("OSError. time retrieval abandoned")
#         return (0, 0, 0, 0, 0, 0, 0, 0)       # 8-tuple to match a real time
#     offset = ET_OFFSET * 3600   # EDT; use -4
#                                 # EST; use -5
#     t = time.localtime(time.time() + offset)
#     return t     # 8-tuple

async def main():
# --- wifi startup
    import boris.secrets as secrets
    await wifi_connect(ssid=secrets.WIFI_SSID, password=secrets.WIFI_PASSWORD,
                 hostname='Boris')

#   boris_time = get_time()
#   print(f"Boris time: {boris_time}")
#   hh = boris_time[3]
#   mm = boris_time[4]
#   ss = boris_time[5]
#   print(hh, mm, ss)
#
#   We'll use the time in a later update when we set hours for the Awake/Asleep activities

    await asyncio.gather(
        heart_beat(led_onboard),
        boris_eyes(),
        clock(),
        app.start_server(port=IP_PORT),
    )

# ---------------------------------------------------------------------
# Start here
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
