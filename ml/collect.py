import serial
import os
import time
import sys

PORT = "COM3"
TARGET_SAMPLES = 200

print("Which gesture are you recording?")
# Add 'fist' to the prompt
GESTURE = input("Options (left, right, up, down, twist): ").strip().lower()

# Add a serial trigger character for the new gesture (e.g., b'f')
triggers = {"left": b'l', "right": b'r', "up": b'u', "down": b'd', "twist": b't'}
if GESTURE not in triggers:
    print("Invalid gesture. Exiting.")
    sys.exit()

CHAR_TRIGGER = triggers[GESTURE]
out_dir = f"ml/data/{GESTURE}"
os.makedirs(out_dir, exist_ok=True)

try:
    with serial.Serial(PORT, 115200, timeout=1) as ser:
        # Check how many we already have so we don't overwrite
        current = len([f for f in os.listdir(out_dir) if f.endswith('.csv')])
        
        if current >= TARGET_SAMPLES:
            print(f"You already have {current} samples for {GESTURE}!")
            sys.exit()
            
        print(f"\n[{GESTURE.upper()}] We need {TARGET_SAMPLES - current} more samples.")
        
        while current < TARGET_SAMPLES:
            # Wait for you to press Enter before triggering the ESP32
            input(f"\n--- Recording {current + 1}/{TARGET_SAMPLES} --- Press ENTER when ready to flick...")
            print(">>> FLICK NOW! <<<")
            
            # Send the trigger character to the ESP32
            ser.write(CHAR_TRIGGER)
            ser.flush()
            
            buffer = []
            recording = False
            
            # Listen for exactly 1.5 seconds to grab the data chunk
            start_time = time.time()
            while time.time() - start_time < 1.5:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line == "---START---":
                    recording = True
                elif line == "---END---":
                    break
                elif recording and line:
                    buffer.append(line)
                    
            # Verify we got exactly 100 samples + 1 header row
            if len(buffer) == 101: 
                current += 1
                with open(f"{out_dir}/sample_{current}.csv", "w") as f:
                    f.write("\n".join(buffer))
                print("-> Captured successfully.")
            else:
                print(f"-> Bad capture (Got {len(buffer)-1} samples). Try this one again.")
                
        print(f"\nDone! You now have {TARGET_SAMPLES} samples for {GESTURE}.")
        print("Run the script again to do the next gesture!")
        
except KeyboardInterrupt:
    print("\nCollection paused. You can restart the script to resume where you left off.")
