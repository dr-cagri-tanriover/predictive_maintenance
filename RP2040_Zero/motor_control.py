import json
from uart_primitives import MessageType, SourceId
from uart_frames import build_frame

_MAX_DUTY_U16 = 65535  # Supported 100% duty cycle in U16

# List handler function names to handle each received UART message based on type field.
_MSG_HANDLER_MAP = {
    MessageType.SET_WAVEFORM_SEQ: "update_waveform_seq",
    MessageType.GET_WAVEFORM_SEQ: "read_waveform_seq",
    MessageType.SET_BRAKE_SEQ: "update_brake_seq",
    MessageType.SET_PWM_FREQ: "update_pwm_Hz",
}

class MotorControl:
    def __init__(self):
        self.waveform_seq = [] # list of lists where each list inside is [duty,duration] and duty out of 100  value: duration in seconds (duty 100 means 100% on)
        self.brake_seq = []  # List of lists where each list inside is [level,duration] where levels are 0,1,2,3,4 and value: duration in seconds (level = 0 is no brake applied.)
        self.pwm_Hz = 1000 # frequency of the PWM signal in Hz (Default = 1000 Hz)

    def get_U16_duty(self, waveform_seq_ID):
        duty_percent = self.waveform_seq[waveform_seq_ID][0]  # duty percent out of 100
        return int(duty_percent * _MAX_DUTY_U16 / 100)

    def get_duration_sec(self, waveform_seq_ID):
        return self.waveform_seq[waveform_seq_ID][1]  # duration in seconds

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
        #print(f"Waveform sequence updated successfully.")
        # Echo the current waveform sequence as UART payload.
        return self.generate_waveform_seq_response()

    def update_brake_seq(self, binary_paylad):
        return None

    def update_pwm_Hz(self, binary_paylad):
        return None

    ##### Read back methods

    def read_waveform_seq(self, binary_paylad=None):
        # Echo current waveform sequence in use.
        return self.generate_waveform_seq_response()

    def read_brake_seq(self, binary_paylad=None):
        return self.brake_seq

    def read_pwm_Hz(self, binary_paylad=None):
        return self.pwm_Hz

    ##### UART response messages

    def generate_waveform_seq_response(self):
        return build_frame(
            MessageType.CURRENT_WAVEFORM_SEQ,
            SourceId.RP2040_ZERO,
            payload=json.dumps(self.waveform_seq).encode("utf-8")
            )