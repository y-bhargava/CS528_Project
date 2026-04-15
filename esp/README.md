# ESP32-S3 Firmware (ESP-IDF)

This directory is now scaffolded as an ESP-IDF project.

## Board

- ESP32-S3-DevKitC-1
- MPU6050 wiring:
  - `VCC -> 3V3`
  - `GND -> GND`
  - `SDA -> GPIO8`
  - `SCL -> GPIO9`

## Build/Flash

1. Install ESP-IDF and export environment (`idf.py` must be on PATH).
2. From this folder:

```bash
cd esp
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/cu.usbmodemXXXX flash monitor
```

## Notes

- Firmware source is in `main/main.cpp`.
- The app emits NDJSON gesture messages over USB serial, e.g.:

```json
{"type":"gesture","name":"left","source":"esp"}
```

- Host side can consume this via:

```bash
python3 -u host/main.py --serial-port /dev/cu.usbmodemXXXX --serial-baud 115200
```
