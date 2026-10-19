import time
import unittest

from demo.hardware import MockArduinoSerial
from demo.protocol import parse_telemetry_line


class MockHardwareTest(unittest.TestCase):
    def read_telemetry(self, mock, predicate):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = mock.readline().decode("utf-8", errors="replace").strip()
            telemetry = parse_telemetry_line(line)
            if telemetry and predicate(telemetry):
                return telemetry
        self.fail("No llegó la telemetría esperada del mock")

    def test_policy_bpm_scales_and_stop_clears_the_signal(self):
        mock = MockArduinoSerial()
        try:
            no_policy = self.read_telemetry(mock, lambda data: data.get("signal_ok") == "0")
            self.assertEqual(no_policy.get("bpm"), "0")

            expected_bpms = {
                "awareness": "68",
                "reassure": "82",
                "breath": "101",
                "calm_down": "124",
            }
            for policy, expected_bpm in expected_bpms.items():
                mock.set_policy(policy)
                telemetry = self.read_telemetry(
                    mock,
                    lambda data, selected=policy, bpm=expected_bpm: (
                        data.get("policy") == selected and data.get("bpm") == bpm
                    ),
                )
                self.assertEqual(telemetry.get("bpm"), expected_bpm)

            mock.write(b"STOP\n")
            stopped = self.read_telemetry(mock, lambda data: data.get("signal_ok") == "0")
            self.assertEqual(stopped.get("bpm"), "0")
        finally:
            mock.close()


if __name__ == "__main__":
    unittest.main()
