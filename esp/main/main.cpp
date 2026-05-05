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

#include "svm_model.h"   // contains classifier + scale_features()

#define I2C_MASTER_SCL_IO    GPIO_NUM_9
#define I2C_MASTER_SDA_IO    GPIO_NUM_8
#define I2C_MASTER_FREQ_HZ   400000
#define I2C_MASTER_NUM       I2C_NUM_0

#define SAMPLE_PERIOD_MS        10
#define CAPTURE_SIZE            100   // 1 second at 10 ms/sample
#define GYRO_TRIGGER_THRESHOLD  50.0f

static mpu6050_handle_t mpu6050 = NULL;
Eloquent::ML::Port::SVM classifier;
const char* gesture_names[] = {"left", "right", "up", "down", "twist"};

float ring_ax[CAPTURE_SIZE], ring_ay[CAPTURE_SIZE], ring_az[CAPTURE_SIZE];
float ring_gx[CAPTURE_SIZE], ring_gy[CAPTURE_SIZE], ring_gz[CAPTURE_SIZE];
float cap_ax[CAPTURE_SIZE],  cap_ay[CAPTURE_SIZE],  cap_az[CAPTURE_SIZE];
float cap_gx[CAPTURE_SIZE],  cap_gy[CAPTURE_SIZE],  cap_gz[CAPTURE_SIZE];

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
// Feature extraction — 18 features matching train_svm.py:
//   max[6], min[6], std[6]
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
        features[6 + i]  = min_val;
        features[12 + i] = sqrtf(var / CAPTURE_SIZE);
    }
}

// ---------------------------------------------------------------------------
// Shared: unroll ring buffer → cap arrays, extract, scale, predict, emit
// ---------------------------------------------------------------------------
void run_prediction(int head) {
    for (int i = 0; i < CAPTURE_SIZE; i++) {
        int idx = (head + i) % CAPTURE_SIZE;
        cap_ax[i] = ring_ax[idx]; cap_ay[i] = ring_ay[idx]; cap_az[i] = ring_az[idx];
        cap_gx[i] = ring_gx[idx]; cap_gy[i] = ring_gy[idx]; cap_gz[i] = ring_gz[idx];
    }

    float features[18];
    extract_features(features);
    scale_features(features);   // ← apply StandardScaler before SVM

    int class_idx = classifier.predict(features);
    printf("{\"type\":\"gesture\",\"name\":\"%s\",\"source\":\"svm\"}\n",
           gesture_names[class_idx]);
}

// ---------------------------------------------------------------------------
// Gesture task — autonomous detection for main.py
// ---------------------------------------------------------------------------
void gesture_task(void *pvParameters) {
    mpu6050_acce_value_t acce;
    mpu6050_gyro_value_t gyro;
    int  head             = 0;
    int  samples          = 0;
    bool cooldown_active  = false;

    while (1) {
        // Check for 't' command from predict.py (non-blocking)
        uint8_t ch = 0;
        int len = uart_read_bytes(UART_NUM_0, &ch, 1, 0);
        if (len > 0 && ch == 't') {
            // Capture exactly 100 samples on demand, output as CSV for predict.py
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
            samples = 0;
            head    = 0;
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }

        mpu6050_get_acce(mpu6050, &acce);
        mpu6050_get_gyro(mpu6050, &gyro);

        ring_ax[head] = acce.acce_x; ring_ay[head] = acce.acce_y; ring_az[head] = acce.acce_z;
        ring_gx[head] = gyro.gyro_x; ring_gy[head] = gyro.gyro_y; ring_gz[head] = gyro.gyro_z;
        head = (head + 1) % CAPTURE_SIZE;
        if (samples < CAPTURE_SIZE) samples++;

        bool motion = (fabsf(gyro.gyro_x) > GYRO_TRIGGER_THRESHOLD ||
                       fabsf(gyro.gyro_y) > GYRO_TRIGGER_THRESHOLD ||
                       fabsf(gyro.gyro_z) > GYRO_TRIGGER_THRESHOLD);

        if (samples == CAPTURE_SIZE && motion && !cooldown_active) {
            // Capture 40 more samples to catch the tail of the gesture
            for (int i = 0; i < 40; i++) {
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
                mpu6050_get_acce(mpu6050, &acce);
                mpu6050_get_gyro(mpu6050, &gyro);
                ring_ax[head] = acce.acce_x; ring_ay[head] = acce.acce_y; ring_az[head] = acce.acce_z;
                ring_gx[head] = gyro.gyro_x; ring_gy[head] = gyro.gyro_y; ring_gz[head] = gyro.gyro_z;
                head = (head + 1) % CAPTURE_SIZE;
            }

            run_prediction(head);

            vTaskDelay(pdMS_TO_TICKS(800));
            samples = 0;
            head    = 0;
        }

        vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

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
