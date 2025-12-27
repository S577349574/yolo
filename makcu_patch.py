# makcu_patch.py
from makcu.connection import SerialTransport

def _handle_button_data_silent(self, byte_val: int):
    if byte_val == self._last_button_mask:
        return

    changed_bits = byte_val ^ self._last_button_mask

    for bit in range(8):
        if changed_bits & (1 << bit):
            is_pressed = bool(byte_val & (1 << bit))

            if is_pressed:
                self._button_states |= (1 << bit)
            else:
                self._button_states &= ~(1 << bit)

            if self._button_callback and bit < len(self.BUTTON_ENUM_MAP):
                try:
                    self._button_callback(self.BUTTON_ENUM_MAP[bit], is_pressed)
                except Exception:
                    pass

    self._last_button_mask = byte_val


def apply():
    SerialTransport._handle_button_data = _handle_button_data_silent
