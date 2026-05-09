#include <stdio.h>
#include <string.h>
#include <math.h>

extern "C" {
    #include "freertos/FreeRTOS.h"
    #include "freertos/task.h"
    #include "driver/i2c.h"
    #include "driver/uart.h"
    #include "mpu6050.h"
}

#include "svm_model.h"

#define I2C_MASTER_SCL_IO    GPIO_NUM_9
#define I2C_MASTER_SDA_IO    GPIO_NUM_8
#define I2C_MASTER_FREQ_HZ   400000
#define I2C_MASTER_NUM       I2C_NUM_0

#define SAMPLE_PERIOD_MS        10
#define CAPTURE_SIZE            100
#define GYRO_TRIGGER_THRESHOLD  50.0f
#define PRE_TRIGGER_SAMPLES     35
#define POST_TRIGGER_SAMPLES    (CAPTURE_SIZE - PRE_TRIGGER_SAMPLES)

static mpu6050_handle_t mpu6050 = NULL;
Eloquent::ML::Port::LDA classifier;
const char* gesture_names[] = {"left", "right", "up", "down", "twist"};

// Capture buffer (fed to feature extractor)
float cap_ax[CAPTURE_SIZE], cap_ay[CAPTURE_SIZE], cap_az[CAPTURE_SIZE];
float cap_gx[CAPTURE_SIZE], cap_gy[CAPTURE_SIZE], cap_gz[CAPTURE_SIZE];

// Pre-trigger ring buffer (~150 ms of history)
float pre_ax[PRE_TRIGGER_SAMPLES], pre_ay[PRE_TRIGGER_SAMPLES], pre_az[PRE_TRIGGER_SAMPLES];
float pre_gx[PRE_TRIGGER_SAMPLES], pre_gy[PRE_TRIGGER_SAMPLES], pre_gz[PRE_TRIGGER_SAMPLES];
int   pre_head = 0;

// ---------------------------------------------------------------------------
// I2C init
// ---------------------------------------------------------------------------
static esp_err_t i2c_bus_init(void) {
    i2c_config_t conf = {};
    conf.mode             = I2C_MODE_MASTER;
    conf.sda_io_num       = I2C_MASTER_SDA_IO;
    conf.scl_io_num       = I2C_MASTER_SCL_IO;
    conf.sda_pullup_en    = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en    = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = I2C_MASTER_FREQ_HZ;
    i2c_param_config(I2C_MASTER_NUM, &conf);
    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0);
}

// ---------------------------------------------------------------------------
// Feature extraction — 18 features: max[6], min[6], std[6]
// ---------------------------------------------------------------------------
void extract_features(float* features) {
    float* axes[6] = {cap_ax, cap_ay, cap_az, cap_gx, cap_gy, cap_gz};
    for (int i = 0; i < 6; i++) {
        float max_val = -1e9f, min_val = 1e9f, sum = 0.0f;
        for (int j = 0; j < CAPTURE_SIZE; j++) {
            float v = axes[i][j];
            if (v > max_val) max_val = v;
            if (v < min_val) min_val = v;
            sum += v;
        }
        float mean = sum / CAPTURE_SIZE;
        float var  = 0.0f;
        for (int j = 0; j < CAPTURE_SIZE; j++) {
            float d = axes[i][j] - mean;
            var += d * d;
        }
        features[i]      = max_val;
        features[6  + i] = min_val;
        features[12 + i] = sqrtf(var / CAPTURE_SIZE);
        features[18 + i] = mean;   // ← add this
    }
}

// ---------------------------------------------------------------------------
// Gesture task
// ---------------------------------------------------------------------------
void gesture_task(void *pvParameters) {
    mpu6050_acce_value_t acce;
    mpu6050_gyro_value_t gyro;
    bool in_cooldown = false;

    while (1) {
        // --- 't' command: stream raw CSV for predict.py ---
        uint8_t ch = 0;
        if (uart_read_bytes(UART_NUM_0, &ch, 1, 0) > 0 && ch == 't') {
            printf("---START---\n");
            printf("ax,ay,az,gx,gy,gz\n");
            for (int i = 0; i < CAPTURE_SIZE; i++) {
                mpu6050_get_acce(mpu6050, &acce);
                mpu6050_get_gyro(mpu6050, &gyro);
                printf("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
                       acce.acce_x, acce.acce_y, acce.acce_z,
                       gyro.gyro_x, gyro.gyro_y, gyro.gyro_z);
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            }
            printf("---END---\n");
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }

        // --- Poll IMU ---
        mpu6050_get_acce(mpu6050, &acce);
        mpu6050_get_gyro(mpu6050, &gyro);

        bool motion = (fabsf(gyro.gyro_x) > GYRO_TRIGGER_THRESHOLD ||
                       fabsf(gyro.gyro_y) > GYRO_TRIGGER_THRESHOLD ||
                       fabsf(gyro.gyro_z) > GYRO_TRIGGER_THRESHOLD);

        if (motion && !in_cooldown) {
            in_cooldown = true;

            // 1. Unroll pre-trigger ring buffer into start of cap arrays
            //    This gives us ~150 ms before the threshold fired, matching
            //    the training window from Code 1 (Enter -> 150 ms -> capture)
            for (int i = 0; i < PRE_TRIGGER_SAMPLES; i++) {
                int idx = (pre_head + i) % PRE_TRIGGER_SAMPLES;
                cap_ax[i] = pre_ax[idx]; cap_ay[i] = pre_ay[idx]; cap_az[i] = pre_az[idx];
                cap_gx[i] = pre_gx[idx]; cap_gy[i] = pre_gy[idx]; cap_gz[i] = pre_gz[idx];
            }

            // 2. Capture remaining 85 samples forward
            for (int i = PRE_TRIGGER_SAMPLES; i < CAPTURE_SIZE; i++) {
                mpu6050_get_acce(mpu6050, &acce);
                mpu6050_get_gyro(mpu6050, &gyro);
                cap_ax[i] = acce.acce_x; cap_ay[i] = acce.acce_y; cap_az[i] = acce.acce_z;
                cap_gx[i] = gyro.gyro_x; cap_gy[i] = gyro.gyro_y; cap_gz[i] = gyro.gyro_z;
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            }

            // 3. Extract, scale, predict
            float features[24];
            extract_features(features);
            scale_features(features);
            int class_idx = classifier.predict(features);
            printf("{\"type\":\"gesture\",\"name\":\"%s\",\"source\":\"lda\"}\n",
                   gesture_names[class_idx]);

            // 4. Cooldown to prevent re-triggering on gesture tail
            vTaskDelay(pdMS_TO_TICKS(800));
            in_cooldown = false;

        } else {
            // Keep rolling pre-trigger history while idle
            pre_ax[pre_head] = acce.acce_x; pre_ay[pre_head] = acce.acce_y; pre_az[pre_head] = acce.acce_z;
            pre_gx[pre_head] = gyro.gyro_x; pre_gy[pre_head] = gyro.gyro_y; pre_gz[pre_head] = gyro.gyro_z;
            pre_head = (pre_head + 1) % PRE_TRIGGER_SAMPLES;
        }

        vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
extern "C" void app_main(void) {
    ESP_ERROR_CHECK(i2c_bus_init());
    mpu6050 = mpu6050_create(I2C_MASTER_NUM, 0x68);
    mpu6050_config(mpu6050, ACCE_FS_4G, GYRO_FS_500DPS);
    mpu6050_wake_up(mpu6050);

    uart_config_t uart_config = {};
    uart_config.baud_rate  = 115200;
    uart_config.data_bits  = UART_DATA_8_BITS;
    uart_config.parity     = UART_PARITY_DISABLE;
    uart_config.stop_bits  = UART_STOP_BITS_1;
    uart_config.flow_ctrl  = UART_HW_FLOWCTRL_DISABLE;
    uart_config.source_clk = UART_SCLK_DEFAULT;
    uart_param_config(UART_NUM_0, &uart_config);
    uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);

    xTaskCreate(gesture_task, "gesture_task", 8192, NULL, 5, NULL);
}