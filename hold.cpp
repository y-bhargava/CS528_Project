#include <stdio.h>
#include <string.h>
#include <math.h>

extern "C" {
    #include "freertos/FreeRTOS.h"
    #include "freertos/task.h"
    #include "driver/i2c.h"
    #include "driver/uart.h"
    #include "mpu6050.h"
    #include "esp_log.h"
}

// Include your exported machine learning model
#include "svm_model.h"

#define I2C_MASTER_SCL_IO    GPIO_NUM_9
#define I2C_MASTER_SDA_IO    GPIO_NUM_8
#define I2C_MASTER_FREQ_HZ   400000
#define I2C_MASTER_NUM       I2C_NUM_0

#define SAMPLE_PERIOD_MS      10
#define CAPTURE_SIZE          100

static mpu6050_handle_t mpu6050 = NULL;

// Buffers to hold 1 full second of data (100 samples)
float ax[CAPTURE_SIZE], ay[CAPTURE_SIZE], az[CAPTURE_SIZE];
float gx[CAPTURE_SIZE], gy[CAPTURE_SIZE], gz[CAPTURE_SIZE];

// The alphabetical order outputted by scikit-learn
const char* gesture_names[] = {"left", "right", "up", "down", "twist"};

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

void run_prediction() {
    float features[18];
    float* axes[6] = {ax, ay, az, gx, gy, gz};

    float max_vals[6], min_vals[6], std_vals[6];  // ← collect separately

    for (int a = 0; a < 6; a++) {
        float max_val = -99999.0f, min_val = 99999.0f, sum = 0.0f;

        for (int i = 0; i < CAPTURE_SIZE; i++) {
            float val = axes[a][i];
            if (val > max_val) max_val = val;
            if (val < min_val) min_val = val;
            sum += val;
        }

        float mean = sum / CAPTURE_SIZE;
        float variance = 0.0f;
        for (int i = 0; i < CAPTURE_SIZE; i++) {
            float d = axes[a][i] - mean;
            variance += d * d;
        }

        max_vals[a] = max_val;
        min_vals[a] = min_val;
        std_vals[a] = sqrtf(variance / CAPTURE_SIZE);
    }

    // Match Python: [all_max, all_min, all_std]
    for (int a = 0; a < 6; a++) {
        features[a]      = max_vals[a];   // idx 0–5
        features[6 + a]  = min_vals[a];   // idx 6–11
        features[12 + a] = std_vals[a];   // idx 12–17
    }

    scale_features(features);

    Eloquent::ML::Port::LDA classifier;
    int class_idx = classifier.predict(features);
    printf("{\"type\":\"gesture\",\"name\":\"%s\",\"source\":\"lda\"}\n", gesture_names[class_idx]);
}

extern "C" void app_main(void) {
    ESP_ERROR_CHECK(i2c_bus_init());
    mpu6050 = mpu6050_create(I2C_MASTER_NUM, 0x68);
    mpu6050_config(mpu6050, ACCE_FS_4G, GYRO_FS_500DPS);
    mpu6050_wake_up(mpu6050);

    // Configure UART so the ESP32 can listen for the Enter key
    uart_config_t uart_config = {};
    uart_config.baud_rate = 115200;
    uart_config.data_bits = UART_DATA_8_BITS;
    uart_config.parity    = UART_PARITY_DISABLE;
    uart_config.stop_bits = UART_STOP_BITS_1;
    uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    
    uart_param_config(UART_NUM_0, &uart_config);
    uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);

    mpu6050_acce_value_t acce;
    mpu6050_gyro_value_t gyro;

    printf("\n[READY] Firmware loaded. Press 'Enter' in the terminal to trigger a gesture recording.\n");

    while(1) {
        uint8_t rx_byte;
        int len = uart_read_bytes(UART_NUM_0, &rx_byte, 1, pdMS_TO_TICKS(10));

        // Wait for a character to be sent over serial
        if (len > 0) {
            // Flush any immediate subsequent characters (like \r\n combinations)
            uart_flush(UART_NUM_0);

            // Wait 150ms to account for human reaction time (matching collect.py)
            vTaskDelay(pdMS_TO_TICKS(150)); 

            // Record exactly 100 samples moving forward in time
            for (int i = 0; i < CAPTURE_SIZE; i++) {
                mpu6050_get_acce(mpu6050, &acce);
                mpu6050_get_gyro(mpu6050, &gyro);
                
                ax[i] = acce.acce_x; 
                ay[i] = acce.acce_y; 
                az[i] = acce.acce_z;
                gx[i] = gyro.gyro_x; 
                gy[i] = gyro.gyro_y; 
                gz[i] = gyro.gyro_z;
                
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            }

            // The buffer is now full of the perfect gesture window. Run the math.
            run_prediction();
        }
    }
}