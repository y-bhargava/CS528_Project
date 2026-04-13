#include <stdio.h>
#include <string.h>
#include <math.h>

// SVM header is no longer used for inference, but kept in case you want
// to compare outputs. You can remove this include if you want a clean build.
// #include "svm_model.h"
// #include "scaler_config.h"

extern "C" {
    #include "freertos/FreeRTOS.h"
    #include "freertos/task.h"
    #include "driver/i2c.h"
    #include "driver/uart.h"
    #include "mpu6050.h"
    #include "esp_log.h"
}

#define I2C_MASTER_SCL_IO    1
#define I2C_MASTER_SDA_IO    0
#define I2C_MASTER_FREQ_HZ   400000
#define I2C_MASTER_NUM       I2C_NUM_0

#define SAMPLE_PERIOD_MS     10
#define CAPTURE_SIZE         80    // 800ms — enough to catch the full flick peak

// -----------------------------------------------------------------------
// WHY THE SVM ALWAYS RETURNED LEFT:
//
//   The model was trained on 400-sample windows of *repeated* gesture
//   cycles (4 seconds of continuous up/up/up or left/left/left).
//   A single real-time flick gives ~20 samples of real motion then returns
//   to rest — the SVM has never seen that feature shape and defaults to
//   whichever class sits closest to a near-flat signal, which was LEFT.
//   No amount of buffer tuning fixes a training/inference distribution
//   mismatch this large.
//
// THE FIX — Rule-based classifier:
//
//   Your own signal analysis already tells you the perfect ruleset:
//
//     Gyro X dominates  →  vertical gesture
//       peak_gx > 0     →  UP    (hand pitches upward,  positive X spike)
//       peak_gx < 0     →  DOWN  (hand pitches downward, negative X spike)
//
//     Gyro Z dominates  →  lateral gesture
//       peak_gz > 0     →  LEFT  (hand yaws left,  positive Z spike)
//       peak_gz < 0     →  RIGHT (hand yaws right, negative Z spike)
//
//   This is deterministic, works on a single flick, and matches exactly
//   what the PDF showed in every time-domain and frequency-domain plot.
// -----------------------------------------------------------------------

// Short capture buffer — only needs to hold the flick itself
float cap_gx[CAPTURE_SIZE];
float cap_gz[CAPTURE_SIZE];

static mpu6050_handle_t mpu6050 = NULL;

// -----------------------------------------------------------------------
// Rule-based classifier
//   Returns: 0=UP, 1=DOWN, 2=LEFT, 3=RIGHT
// -----------------------------------------------------------------------
int classify_gesture() {
    // Find the signed peak on each relevant axis across the capture window
    float peak_gx = 0.0f;
    float peak_gz = 0.0f;

    for (int i = 0; i < CAPTURE_SIZE; i++) {
        if (fabsf(cap_gx[i]) > fabsf(peak_gx)) peak_gx = cap_gx[i];
        if (fabsf(cap_gz[i]) > fabsf(peak_gz)) peak_gz = cap_gz[i];
    }

    // Whichever axis had the larger absolute peak owns this gesture
    if (fabsf(peak_gx) >= fabsf(peak_gz)) {
        // Vertical pitch motion
        return (peak_gx > 0) ? 0 : 1;   // positive = UP, negative = DOWN
    } else {
        // Lateral yaw motion
        return (peak_gz > 0) ? 2 : 3;   // positive = LEFT, negative = RIGHT
    }
}

// -----------------------------------------------------------------------
// I2C init
// -----------------------------------------------------------------------
static esp_err_t i2c_bus_init(void) {
    i2c_config_t conf;
    memset(&conf, 0, sizeof(i2c_config_t));
    conf.mode             = I2C_MODE_MASTER;
    conf.sda_io_num       = I2C_MASTER_SDA_IO;
    conf.scl_io_num       = I2C_MASTER_SCL_IO;
    conf.sda_pullup_en    = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en    = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = I2C_MASTER_FREQ_HZ;
    i2c_param_config(I2C_MASTER_NUM, &conf);
    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0);
}

// -----------------------------------------------------------------------
// Main gesture task
// -----------------------------------------------------------------------
void gesture_task(void *pvParameters) {
    mpu6050_acce_value_t acce;
    mpu6050_gyro_value_t gyro;

    printf("\n========================================\n");
    printf("  [Edge AI] Gesture Controller Ready\n");
    printf("========================================\n");
    printf(">>> Perform a gesture whenever you're ready...\n\n");

    while (1) {
        mpu6050_get_acce(mpu6050, &acce);
        mpu6050_get_gyro(mpu6050, &gyro);

        // Trigger on fast Pitch (X) = UP/DOWN  or  fast Yaw (Z) = LEFT/RIGHT
        if (fabsf(gyro.gyro_z) > 150.0f || fabsf(gyro.gyro_x) > 150.0f) {

            printf("  [*] Flick detected — classifying...\n");

            // Store trigger sample
            cap_gx[0] = gyro.gyro_x;
            cap_gz[0] = gyro.gyro_z;

            // Capture the rest of the flick
            for (int i = 1; i < CAPTURE_SIZE; i++) {
                mpu6050_get_gyro(mpu6050, &gyro);
                cap_gx[i] = gyro.gyro_x;
                cap_gz[i] = gyro.gyro_z;
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            }

            // Classify using axis + sign rules
            int prediction = classify_gesture();

            if (prediction == 0) {
                printf("  [RESULT] --> UP    | CMD:UP\n");
                printf("CMD:UP\n");
            } else if (prediction == 1) {
                printf("  [RESULT] --> DOWN  | CMD:DOWN\n");
                printf("CMD:DOWN\n");
            } else if (prediction == 2) {
                printf("  [RESULT] --> LEFT  | CMD:LEFT\n");
                printf("CMD:LEFT\n");
            } else if (prediction == 3) {
                printf("  [RESULT] --> RIGHT | CMD:RIGHT\n");
                printf("CMD:RIGHT\n");
            }

            // Cooldown to prevent double-firing
            vTaskDelay(pdMS_TO_TICKS(800));

            printf("\n>>> Ready — perform your next gesture...\n\n");
        }

        vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

// -----------------------------------------------------------------------
// Entry point
// -----------------------------------------------------------------------
extern "C" void app_main(void) {
    ESP_ERROR_CHECK(i2c_bus_init());
    mpu6050 = mpu6050_create(I2C_MASTER_NUM, 0x68);
    mpu6050_config(mpu6050, ACCE_FS_4G, GYRO_FS_500DPS);
    mpu6050_wake_up(mpu6050);

    xTaskCreate(gesture_task, "gesture_task", 8192, NULL, 5, NULL);
}