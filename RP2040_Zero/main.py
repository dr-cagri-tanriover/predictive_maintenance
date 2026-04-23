# main.py — asyncio template: polling + timed steps
from machine import Pin, PWM, Timer
import uasyncio as asyncio

# Pin assignments
PWM_OUT_PIN = 2 # Set up PWM on pin GP2
BRAKE_L1_PIN = 5 # Set up brake on pin GP5
BRAKE_L2_PIN = 6 # Set up brake on pin GP6
BRAKE_L3_PIN = 7 # Set up brake on pin GP7
BRAKE_L4_PIN = 8 # Set up brake on pin GP8

UART_TX_PIN = 12 # Set up UART0 TX on pin GP12
UART_RX_PIN = 13 # Set up UART0 RX on pin GP13

#IRQ_BLUE_LED_PIN = 7  # GP7 drives a separate LED via Timer IRQ
#IRQ_YELLOW_LED_PIN = 8  # GP8 drives a separate LED via Timer IRQ

# Parameter initializations
PWM_FREQ_HZ = 1000  # Frequency of PWM in Hertz
# LED_BLINK_PERIOD_MS = 500  # GP7 toggle period (ms)

# Shared acess device initializations
led = PWM(Pin(PWM_OUT_PIN))
led.freq(PWM_FREQ_HZ)  # Set PWM frequency
brake_l1_pin = Pin(BRAKE_L1_PIN, Pin.OUT, value=0)
brake_l2_pin = Pin(BRAKE_L2_PIN, Pin.OUT, value=0)
brake_l3_pin = Pin(BRAKE_L3_PIN, Pin.OUT, value=0)
brake_l4_pin = Pin(BRAKE_L4_PIN, Pin.OUT, value=0)

# --- Shared state (optional) ---
state = {
  "running": True
}

# After each segment duration, advance waveform (set False to run only the first segment once).
TIMER_IRQ_REPEAT = True

# Waveform components to use to generate a composite waveform to drive the motor.
waveforms = {
            "pwm_25":
                    {
                        "duty": 16384, # duty cycle used
                        "timeSec": 1  # duration of regime
                    },
            "pwm_50":
                    {
                        "duty": 32768, # duty cycle used
                        "timeSec": 1 # duration of regime
                    },
            "pwm_75":
                    {
                        "duty": 49151, # duty cycle used
                        "timeSec": 1 # duration of regime
                    }
             }

# Brake sequence to use to generate a composite waveform to drive the motor.
brake_attribs = {
            "L0":
                    {
                        "timeSec": 2, # 2 seconds of no braking
                        "gpioPin": None  # No GPIO pin to turn on/off
                    },
            "L1":
                    {
                        "timeSec": 7, # duration of regime
                        "gpioPin": brake_l1_pin
                    },
            "L2":
                    {
                        "timeSec": 5, # duration of regime
                        "gpioPin": brake_l2_pin
                    },
            "L3":
                    {
                        "timeSec": 3, # duration of regime
                        "gpioPin": brake_l3_pin
                    },
            "L4":
                    {
                        "timeSec": 1, # duration of regime
                        "gpioPin": brake_l4_pin
                    }
             }

# L0: no brakes applied, L4: full brakes applied
brake_sequence = {0: "L0", 1: "L1", 2: "L2", 3: "L3", 4: "L4"}  # user defined
current_brake_idx = 0  # starting brake index initialized here by user.

composite_waveform_period_seq = {0: "pwm_25", 1: "pwm_50", 2: "pwm_75", 3: "pwm_50"}
current_composite_waveform_idx = 0

# irq_blue_led = Pin(IRQ_BLUE_LED_PIN, Pin.OUT, value=0)
# irq_yellow_led = Pin(IRQ_YELLOW_LED_PIN, Pin.OUT, value=0)

# Dedicated hardware timer for LED blink IRQ (kept independent from waveform logic).
# blue_timer = Timer()
# yellow_timer = Timer()
brake_timer = Timer()

# def _blink_blue_led_irq_cb(_t):
#     irq_blue_led.toggle()

# def _blink_yellow_led_irq_cb(_t):
#     irq_yellow_led.toggle()

def _apply_nextbrake_irq_cb(_t):
  # Fast and effective ISR!
  next_brake_prep_event.set()  # Trigger the next brake state to transition to.

# def start_irq_led_blink(period_ms=LED_BLINK_PERIOD_MS):
#     blue_timer.init(period=period_ms, mode=Timer.PERIODIC, callback=_blink_blue_led_irq_cb)
#     yellow_timer.init(period=int(period_ms/2), mode=Timer.PERIODIC, callback=_blink_yellow_led_irq_cb)


# ---------- Your app tasks ----------
async def task_next_brake_prep():    # This task updates in an event-driven way..
    global current_brake_idx
    global brake_sequence
    global brake_attribs

    await ready_event.wait()  # this task blocks until ready_event.set() runs in main()

    while state["running"]:
      await next_brake_prep_event.wait()  # Yielding back to the scheduler until irq prompts the next brake state to transition to.
      # Timer interrupt set next_brake_prep_event.

      # Turn current brake GPIO pin off
      if brake_attribs[brake_sequence[current_brake_idx]]["gpioPin"] is not None:
        brake_attribs[brake_sequence[current_brake_idx]]["gpioPin"].off()  # stop currently active brake.
      #else since no gpio is applicable to current brake state, there is no gpio to turn off!

      current_brake_idx = (current_brake_idx + 1) % len(brake_sequence)  # next brake sequence index updated.
      brake_state_update()  # runs the current brake state as per current_brake_idx setting. Runs at startup.
      next_brake_prep_event.clear()  # event cleared. Only Timer interrupt will set it again!


async def task_timer_irq_consumer():
    global current_composite_waveform_idx
    global composite_waveform_period_seq
    global waveforms
    
    await ready_event.wait()

    while state["running"]:
        key = composite_waveform_period_seq[current_composite_waveform_idx]
        seg = waveforms[key]
        led.duty_u16(seg["duty"])

        await asyncio.sleep(seg["timeSec"])  # Used instead of Timer() interrupt
        current_composite_waveform_idx = (current_composite_waveform_idx + 1) % len(composite_waveform_period_seq)
        if not TIMER_IRQ_REPEAT:
            break


def brake_state_update():
  global current_brake_idx
  global brake_sequence

  _brake_duration = brake_attribs[brake_sequence[current_brake_idx]]["timeSec"]
  _gpio_pin = brake_attribs[brake_sequence[current_brake_idx]]["gpioPin"]

  brake_timer.init(period=_brake_duration*1000, mode=Timer.ONE_SHOT, callback=_apply_nextbrake_irq_cb)
  # Turn on relevant GPIO to apply the brake
  if _gpio_pin is not None:
    _gpio_pin.on()  # brake is physically applied now
  #else current_brake_idx is "L0", i.e., no brake! 

###########################################################

# Tasks can wait on this after hardware is ready
ready_event = asyncio.Event()  # Starts in the cleared state.
next_brake_prep_event = asyncio.Event()  # Triggers the update of the next brake state to transition to.

async def main():
  # 1) Hardware init (I2C, displays, etc.) — before unblocking tasks
  # start_irq_led_blink()

  brake_state_update()  # runs the current brake state at startup as per current_brake_idx setting.

  # Following line ensures no task runs until hardware is reliably initialized as above!
  ready_event.set()  # any task with await ready_event.wait() is blocked until this line is executed.
  
  # All coroutines are started below, and each starts to run concurrently (time-sliced by awaits in each coroutine).
  # asyncio.gather() continues to run until all coroutines return. Typically they never returh due to infinite while loops in them to continue running.
  # state["running"] = true keeps each task running indefinitely.
  await asyncio.gather(
      task_next_brake_prep(),
      task_timer_irq_consumer(),
  )

# After importing modules and defining globals, the folowing part is read next.
loop = asyncio.new_event_loop()
loop.run_until_complete(main())  # main() gets executed immediately.
loop.run_forever()