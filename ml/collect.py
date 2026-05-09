import argparse
import os
import sys
import time

import serial

DEFAULT_PORT = os.environ.get("HCI_SERIAL_PORT", "COM3")
TARGET_SAMPLES = 200


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect gesture samples from ESP serial stream.")
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Serial port (default: {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--target-samples",
        type=int,
        default=TARGET_SAMPLES,
        help=f"Target number of samples per gesture (default: {TARGET_SAMPLES}).",
    )
    return parser.parse_args()


print("Which gesture are you recording?")
GESTURE = input("Options (left, right, up, down, twist): ").strip().lower()
args = _parse_args()

triggers = {"left": b"l", "right": b"r", "up": b"u", "down": b"d", "twist": b"t"}
if GESTURE not in triggers:
    print("Invalid gesture. Exiting.")
    sys.exit()

CHAR_TRIGGER = triggers[GESTURE]
out_dir = f"ml/data/{GESTURE}"
os.makedirs(out_dir, exist_ok=True)

try:
    with serial.Serial(args.port, 115200, timeout=1) as ser:
        current = len([f for f in os.listdir(out_dir) if f.endswith('.csv')])

        if current >= args.target_samples:
            print(f"You already have {current} samples for {GESTURE}!")
            sys.exit()

        print(f"\n[{GESTURE.upper()}] Collecting from port: {args.port}")
        print(f"[{GESTURE.upper()}] We need {args.target_samples - current} more samples.")

        while current < args.target_samples:
            input(f"\n--- Recording {current + 1}/{args.target_samples} --- Press ENTER when ready to flick...")
            print(">>> FLICK NOW! <<<")

            ser.write(CHAR_TRIGGER)
            ser.flush()

            buffer = []
            recording = False

            start_time = time.time()
            while time.time() - start_time < 1.5:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line == "---START---":
                    recording = True
                elif line == "---END---":
                    break
                elif recording and line:
                    buffer.append(line)

            if len(buffer) == 101:
                current += 1
                with open(f"{out_dir}/sample_{current}.csv", "w") as f:
                    f.write("\n".join(buffer))
                print("-> Captured successfully.")
            else:
                print(f"-> Bad capture (Got {len(buffer)-1} samples). Try this one again.")

        print(f"\nDone! You now have {args.target_samples} samples for {GESTURE}.")
        print("Run the script again to do the next gesture!")

except KeyboardInterrupt:
    print("\nCollection paused. You can restart the script to resume where you left off.")
