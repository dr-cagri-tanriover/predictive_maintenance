import json
from uart_primitives import MessageType, SourceId
from uart_frames import build_frame

_MAX_DUTY_U16 = 65535  # Supported 100% duty cycle in U16

# List handler function names to handle each received UART message based on type field.
_MSG_HANDLER_MAP = {
    MessageType.SET_WAVEFORM_SEQ: "update_waveform_seq",
    MessageType.GET_WAVEFORM_SEQ: "read_waveform_seq",
    MessageType.SET_BRAKE_SEQ: "update_brake_seq",
    MessageType.GET_BRAKE_SEQ: "read_brake_seq",
    MessageType.SET_PWM_FREQ: "update_pwm_Hz",
    MessageType.GET_PWM_FREQ: "read_pwm_Hz",
    MessageType.START_CAPTURE: "set_capture_start",
    MessageType.STOP_CAPTURE: "set_capture_stop",
}

class MotorControl:
    def __init__(self):
        self.waveform_seq = [] # list of lists where each list inside is [duty,duration] and duty out of 100  value: duration in seconds (duty 100 means 100% on)
        self.brake_seq = []  # List of lists where each list inside is [level,duration] where levels are 0,1,2,3,4 and value: duration in seconds (level = 0 is no brake applied.)
        self.pwm_Hz = 1000 # frequency of the PWM signal in Hz (Default = 1000 Hz)

        # Operation states for Pi Zero. These can be queried externally to control async tasks in main.py.
        self.states = {"capture_start": False, "capture_stop": True}

    def get_U16_duty(self, waveform_seq_ID):
        duty_percent = self.waveform_seq[waveform_seq_ID][0]  # duty percent out of 100
        return int(duty_percent * _MAX_DUTY_U16 / 100)

    def get_waveform_duration_sec(self, waveform_seq_ID):
        return self.waveform_seq[waveform_seq_ID][1]  # duration in seconds

    def get_brake_duration_sec(self, brake_seq_ID):
        return self.brake_seq[brake_seq_ID][1]  # duration in seconds

    def get_brake_level(self, brake_seq_ID):
        return self.brake_seq[brake_seq_ID][0]  # brake level (0,1,2,3,4)

    def is_waveform_seq_valid(self):
        return len(self.waveform_seq) > 0

    def is_brake_seq_valid(self):
        return len(self.brake_seq) > 0

    def process_rx_uart_frame(self, frame):
        #t, src, seq = frame["type"], frame["src"], frame["seq"]
        #print("[UART RX] type=0x%02X src=0x%02X seq=%s payload=%r" % (t, src, seq, frame["payload"]))
        func_name_str = _MSG_HANDLER_MAP.get(frame["type"])
        if func_name_str:
            response = getattr(self, func_name_str)(frame["payload"])  # self is passed to the function as argument. The function is called with the binary payload.
        else:
            print(f"No update method found for frame type: {frame['type']}")
            response = None
        return response

    ##### Update methods

    def update_waveform_seq(self, binary_payload):
        """Binary payload is expected to be a list of lists where each list inside is [duty,duration]"""
        # First decode payload binary string to a list of lists for processing.
        self.waveform_seq = json.loads(binary_payload.decode("utf-8"))
        # Echo the current waveform sequence as UART payload.
        return self.generate_waveform_seq_response()

    def update_brake_seq(self, binary_payload):
        """Binary payload is expected to be a list of lists where each list inside is [level,duration]"""
        # First decode payload binary string to a list of lists for processing.
        self.brake_seq = json.loads(binary_payload.decode("utf-8"))
        # Echo the current waveform sequence as UART payload.
        return self.generate_brake_seq_response()

    def update_pwm_Hz(self, binary_payload):
        """PWM Hz as UTF-8 text: one byte per decimal digit (e.g. 1000 Hz -> b'1000'), not a packed binary int."""
        self.pwm_Hz = int(binary_payload.decode("utf-8").strip())
        # Echo the current PWM frequency as UART payload.
        return self.generate_pwm_Hz_response()

    def set_capture_start(self, binary_payload=None):
        self.states["capture_start"] = True  # This will signal the task in main to kick off data capture.
        self.states["capture_stop"] = False  # Capture stop is cleared by capture start.
        return None  # No UART response sent for capture start.

    def set_capture_stop(self, binary_payload=None):
        self.states["capture_stop"] = True  # This will signal the task in main to stop data capture.
        self.states["capture_start"] = False  # Capture start is cleared by capture stop.
        return None  # No UART response sent for capture stop.

    ##### Read back methods

    def read_waveform_seq(self, binary_payload=None):
        # Echo current waveform sequence in use.
        return self.generate_waveform_seq_response()

    def read_brake_seq(self, binary_payload=None):
        return self.generate_brake_seq_response()

    def read_pwm_Hz(self, binary_payload=None):
        return self.generate_pwm_Hz_response()

    ##### UART response messages

    def generate_waveform_seq_response(self):
        return build_frame(
            MessageType.CURRENT_WAVEFORM_SEQ,
            SourceId.RP2040_ZERO,
            payload=json.dumps(self.waveform_seq).encode("utf-8")  # Convert list of lists to JSON string and encode to bytes
            )

    def generate_brake_seq_response(self):
        return build_frame(
            MessageType.CURRENT_BRAKE_SEQ,
            SourceId.RP2040_ZERO,
            payload=json.dumps(self.brake_seq).encode("utf-8")  # Convert list of lists to JSON string and encode to bytes
            )

    def generate_pwm_Hz_response(self):
        return build_frame(
            MessageType.CURRENT_PWM_FREQ,
            SourceId.RP2040_ZERO,
            payload=str(self.pwm_Hz).encode("utf-8")  # Convert integer to string and encode to bytes
            )