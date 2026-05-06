#include <stdio.h>
#include <string.h>

extern "C" {
    #include "freertos/FreeRTOS.h"
    #include "freertos/task.h"
    #include "driver/i2c.h"
    #include "driver/uart.h"
    #include "mpu6050.h"
    #include "esp_log.h"
}

#define I2C_MASTER_SCL_IO    GPIO_NUM_9
#define I2C_MASTER_SDA_IO    GPIO_NUM_8
#define I2C_MASTER_FREQ_HZ   400000
#define I2C_MASTER_NUM       I2C_NUM_0

#define SAMPLE_PERIOD_MS      10
#define NUM_SAMPLES           100   // 1 second at 10 ms/sample

static mpu6050_handle_t mpu6050 = NULL;

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

void hand_gesture(void *pvParameters) {
    mpu6050_acce_value_t acce;
    mpu6050_gyro_value_t gyro;
    uint8_t input_char;

    printf("\n[READY] Send l/r/u/d to record a gesture.\n");

    while (1) {
        int len = uart_read_bytes(UART_NUM_0, &input_char, 1,
                                  pdMS_TO_TICKS(SAMPLE_PERIOD_MS));

        bool trigger = (input_char == 'l' || input_char == 'r' ||
                        input_char == 'u' || input_char == 'd' || input_char == 't');

        if (len > 0 && trigger) {
            // Markers and header must match collect.py exactly
            printf("---START---\n");
            printf("ax,ay,az,gx,gy,gz\n");

            for (int i = 0; i < NUM_SAMPLES; i++) {
                mpu6050_get_acce(mpu6050, &acce);
                mpu6050_get_gyro(mpu6050, &gyro);
                printf("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
                       acce.acce_x, acce.acce_y, acce.acce_z,
                       gyro.gyro_x, gyro.gyro_y, gyro.gyro_z);
                vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            }

            printf("---END---\n");
        }
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

    xTaskCreate(hand_gesture, "hand_gesture", 4096, NULL, 5, NULL);
}