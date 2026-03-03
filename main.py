
import asyncio
import machine
import utime

# make global to turn off later.
led_onboard = None

# pin assignments
left_p = ["GP16", "GP17", "GP18"]
rite_p = ["GP19", "GP20", "GP21"]
# Note: Pin 1 is: "GP1", not "GP01"

# Hold list for the pin objects
left_e = [None, None, None]
rite_e = [None, None, None]

async def heart_beat(led_onboard):
    while True:
#   Can't catch the keyboard interrupt in this or other tasks - feature of micropython     try:
        led_onboard.toggle()
        await asyncio.sleep(1)

async def boris_eyes():
    blink_step = 0.10
    blink_pause = 0.75
    eyes_sleep = 8.0
    eyes_awake = 8.0
    blinks = 4
    
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
    opcl_eye(left_e, 0)
    opcl_eye(rite_e, 0)
    await toggle_eyes(left_e, rite_e, [0,1,2])  # on

    while True:
#       Eyes open with closed blinking
        for _ in range(blinks):
            await asyncio.sleep(eyes_sleep)
            await blink_eyes_clos(left_e, rite_e)
            
        await asyncio.sleep(eyes_awake)
        await toggle_eyes(left_e, rite_e, [2,1,0])  # off
        for _ in range(blinks):
            await asyncio.sleep(eyes_awake)
            await blink_eyes_open(left_e, rite_e)

        await asyncio.sleep(eyes_sleep)
        await toggle_eyes(left_e, rite_e, [0,1,2])  # on

async def main():
#   setup tasks
    await asyncio.gather(heart_beat(led_onboard), boris_eyes())

if __name__ == "__main__":
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

        print("Byebye from boris-eyes!")
