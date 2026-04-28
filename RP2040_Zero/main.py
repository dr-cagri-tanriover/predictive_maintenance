# main.py — asyncio template: polling + timed steps
from machine import Pin, PWM, Timer, UART
import uasyncio as asyncio
from motor_control import MotorControl
# Be sure to copy the required *.py files from utilities to RP2040 for the following to work !
from uart_frames import FrameDecoder, build_frame
from uart_primitives import SourceId, MessageType

# Pin assignments
PWM_OUT_PIN = 2 # Set up PWM on pin GP2
BRAKE_L1_PIN = 5 # Set up brake on pin GP5
BRAKE_L2_PIN = 6 # Set up brake on pin GP6
BRAKE_L3_PIN = 7 # Set up brake on pin GP7
BRAKE_L4_PIN = 8 # Set up brake on pin GP8

UART_TX_PIN = 12 # Set up UART0 TX on pin GP12
UART_RX_PIN = 13 # Set up UART0 RX on pin GP13
UART_BAUD = 115200  # must match the Pi / peer

mco = MotorControl()  # Motor control object initialized here.

# Shared acess device initializations
led = PWM(Pin(PWM_OUT_PIN))
led.freq(mco.pwm_Hz)  # Get PWM frequency
brake_l1_pin = Pin(BRAKE_L1_PIN, Pin.OUT, value=0)
brake_l2_pin = Pin(BRAKE_L2_PIN, Pin.OUT, value=0)
brake_l3_pin = Pin(BRAKE_L3_PIN, Pin.OUT, value=0)
brake_l4_pin = Pin(BRAKE_L4_PIN, Pin.OUT, value=0)

brake_level_gpio_map = {
  0: None,  # no brake is applied (i.e., all brake gpio pins are turned off)
  1: brake_l1_pin, # brake level 1 is applied to brake_l1_pin (lowest brake level)
  2: brake_l2_pin, # brake level 2 is applied to brake_l2_pin 
  3: brake_l3_pin, # brake level 3 is applied to brake_l3_pin
  4: brake_l4_pin  # brake level 4 is applied to brake_l4_pin
}

# --- Shared state (optional) ---
state = {
  "running": True
}

# After each segment duration, advance waveform (set False to run only the first segment once).
TIMER_IRQ_REPEAT = True

current_brake_idx = 0  # starting brake index initialized here.
current_composite_waveform_idx = 0  # starting waveform index initialized here.

# Dedicated hardware timer for LED blink IRQ (kept independent from waveform logic).
brake_timer = Timer()

# --- UART0 (GP12 TX / GP13 RX): nonblocking driver + uasyncio tasks -------------
# timeout=0 keeps reads nonblocking; RX task polls uart.any() and yields often.
uart = UART(
    0,
    UART_BAUD,
    tx=Pin(UART_TX_PIN),
    rx=Pin(UART_RX_PIN),
    bits=8,
    parity=None,
    stop=1,
    timeout=0,
)

# many MicroPython uasyncio builds have no asyncio.Queue; use a list FIFO.
# (Some MP builds require iterable+maxlen for collections.deque — plain list is safest.)
uart_tx_buf = []
_rx_decoder = FrameDecoder()
_build_frame = build_frame


async def _handle_uart_frame(frame):
    """Full UART frame received. ROute it to the correct processing function next."""
    global mco  # object that stores all current motor related attributes.

    t, src, seq = frame["type"], frame["src"], frame["seq"]
    print("[UART RX] type=0x%02X src=0x%02X seq=%s payload=%r" % (t, src, seq, frame["payload"]))
    response = mco.process_rx_uart_frame(frame)
    if response != None:
      # Response is a valid UART frame. Queue it for transmission.
      uart_tx_buf.append(response)

async def task_uart_rx():
    """Read UART in small chunks, decode framed packets, keep scheduling fair."""
    await ready_event.wait()
    while state["running"]:
        n = uart.any()
        if n > 0:
            chunk = uart.read(min(n, 256))
            if chunk:
                for fr in _rx_decoder.feed(chunk):
                    await _handle_uart_frame(fr)
        # Tiny yield: balance latency vs CPU (use sleep_ms(0) for max responsiveness).
        await asyncio.sleep_ms(1)

    return

async def task_uart_tx():
    """Drain uart_tx_buf and write to UART."""
    await ready_event.wait()
    while state["running"]:
        if uart_tx_buf:
            item = uart_tx_buf.pop(0)
            if item and isinstance(item, (bytes, bytearray, memoryview)):
                uart.write(item)
        else:
            await asyncio.sleep_ms(1)  # yield; wake quickly when work arrives

# Optional: one-time startup frame to the peer.
async def task_uart_hello_once():
    await ready_event.wait()  # happens once after power up !
    p = b"RP2040-ready"
    fr = _build_frame(MessageType.ALIVE_PING, SourceId.RP2040_ZERO, payload=p)
    uart_tx_buf.append(fr)
    await asyncio.sleep(0)  # yield so task_uart_tx can run
    return

async def task_check_capture_start():
    # Checks to see if capture start is triggered by Pi3.
    global mco
    global data_capture_start_event
    global data_capture_stop_event

    await ready_event.wait()

    while state["running"]:
        if mco.states.get("capture_start"):
          # Capture is started by Pi3
          data_capture_start_event.set()  # Capture start event set. Only Pi3 capture stop UART message will clear it.
          data_capture_stop_event.clear()  # Capture stop event cleared. Only Pi3 capture stop UART message will set it again.
          await data_capture_stop_event.wait()  # Wait on data capture stop event to be set before checking for capture start again.
        else:
          # Capture not triggered yet. Check after some time.
          await asyncio.sleep(0.050)  # 50 ms yield to other functions to run.
    
    return

async def task_check_capture_stop():
    # Checks to see if capture stop is triggered by Pi3.
    global mco
    global data_capture_start_event
    global data_capture_stop_event

    await ready_event.wait()

    while state["running"]:
        if mco.states.get("capture_stop"):
          # Capture is stopped by Pi3
          data_capture_start_event.clear()  # Capture start event cleared. Only Pi3 capture start UART message will set it again.
          data_capture_stop_event.set()  # Capture stop event set. Only Pi3 capture start UART message will clear it again.
          await data_capture_start_event.wait()  # Wait on data capture start event to be set before checking for capture stop again.
        else:
          # Capture not stopped yet. Check after some time.
          await asyncio.sleep(0.050)  # 50 ms yield to other functions to run.
    
    return

def _apply_nextbrake_irq_cb(_t):
  # Fast and effective ISR!
  next_brake_prep_event.set()  # Trigger the next brake state to transition to.


# ---------- Your app tasks ----------
async def task_brake_management():    # This task updates in an event-driven way..
    global current_brake_idx
    global brake_level_gpio_map
    global mco

    await ready_event.wait()  # this task blocks until ready_event.set() runs in main()

    while state["running"]:
      await data_capture_start_event.wait() # Wait on data capture message from Pi3. (If event already set, that's fine too!)
      
      brake_state_update()  # runs the current brake state when data capture starts as per current_brake_idx setting.
      next_brake_prep_event.clear()  # event cleared. Only Timer interrupt will set it again!

      await next_brake_prep_event.wait()  # Yielding back to the scheduler until irq prompts the next brake state to transition to.
      # Timer interrupt set next_brake_prep_event.

      # Turn current brake GPIO pin off
      _brake_level = mco.get_brake_level(current_brake_idx)  # brake level (0,1,2,3,4)
      if brake_level_gpio_map[_brake_level] is not None:
        brake_level_gpio_map[_brake_level].off()  # turn off the current brake GPIO pin.
      #else since no gpio is applicable to current brake state, there is no gpio to turn off!

      current_brake_idx = (current_brake_idx + 1) % len(mco.brake_seq)  # next brake sequence index updated.


async def task_waveform_timer_service():
    global mco  # object that stores all current motor related attributes.
    global current_composite_waveform_idx
    
    await ready_event.wait()

    while state["running"]:
        
        await data_capture_start_event.wait() # Wait on data capture message from Pi3. (If event already set, that's fine too!)

        led.duty_u16(mco.get_U16_duty(current_composite_waveform_idx))

        # TODO - Here, queue a uart Tx message to indicate which waveform is currently being applied with a timestamp.
        await asyncio.sleep(mco.get_waveform_duration_sec(current_composite_waveform_idx))  # Used instead of Timer() interrupt
        current_composite_waveform_idx = (current_composite_waveform_idx + 1) % len(mco.waveform_seq)
        
        if not TIMER_IRQ_REPEAT:  # indefinitely repeats the waveform sequence if TIMER_IRQ_REPEAT is True
            break


def brake_state_update():
  global current_brake_idx
  global brake_level_gpio_map
  global mco

  _brake_duration = mco.get_brake_duration_sec(current_brake_idx)  # stored in seconds
  _brake_level = mco.get_brake_level(current_brake_idx)  # brake level (0,1,2,3,4)
  _gpio_pin = brake_level_gpio_map[_brake_level]  # GPIO pin to turn on/off

  # Update global timer object next to trigger the next brake state to transition to.
  brake_timer.init(period=_brake_duration*1000, mode=Timer.ONE_SHOT, callback=_apply_nextbrake_irq_cb)

  # Turn on relevant GPIO to apply the brake
  if _gpio_pin is not None:
    _gpio_pin.on()  # brake is physically applied now
  #else current_brake_idx is "L0", i.e., no brake! 

###########################################################

# Tasks can wait on this after hardware is ready
ready_event = asyncio.Event()  # Starts in the cleared state.
data_capture_start_event = asyncio.Event()  # Triggers the start of data capture from Pi3.
data_capture_stop_event = asyncio.Event()  # Triggers the stop of data capture from Pi3.
next_brake_prep_event = asyncio.Event()  # Triggers the update of the next brake state to transition to.

async def main():
  # 1) Hardware init (I2C, displays, etc.) — before unblocking tasks
  # start_irq_led_blink()

  # Following line ensures no task runs until hardware is reliably initialized as above!
  ready_event.set()  # any task with await ready_event.wait() is blocked until this line is executed.
  data_capture_stop_event.set()  # Capture stop event set. At power up, capture is stopped by default!

  # All coroutines are started below, and each starts to run concurrently (time-sliced by awaits in each coroutine).
  # asyncio.gather() continues to run until all coroutines return. Typically they never returh due to infinite while loops in them to continue running.
  # state["running"] = true keeps each task running indefinitely.
  await asyncio.gather(
      task_uart_rx(),
      task_uart_tx(),
      task_uart_hello_once(),
      task_brake_management(),
      task_waveform_timer_service(),
      task_check_capture_start(),
      task_check_capture_stop(),
  )

# After importing modules and defining globals, the following part is read next.
loop = asyncio.new_event_loop()
loop.run_until_complete(main())  # main() gets executed immediately.
loop.run_forever()