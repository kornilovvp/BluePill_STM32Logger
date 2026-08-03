/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "usb_device.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "usbd_cdc_if.h"
#include "framer.h"
#include "shell.h"
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;
DMA_HandleTypeDef hdma_adc1;

TIM_HandleTypeDef htim3;
DMA_HandleTypeDef hdma_tim3_ch4_up;

/* USER CODE BEGIN PV */
/* Sampler buffers (spec: Docs/30_Firmware/02 + 06). Ping-pong: one half = one
   SLP block of 32 ticks. adc_buf holds [a1, a2] halfword pairs per tick,
   gpio_buf holds raw GPIOA->IDR snapshots taken by DMA on every TIM3 update. */
#define SMP_HALF_TICKS 32u
static uint16_t adc_buf[2u * SMP_HALF_TICKS * 2u];  /* 128 halfwords, HT at 64  */
static uint16_t gpio_buf[2u * SMP_HALF_TICKS];      /* 64 halfwords             */
static volatile uint8_t  smp_half_ready;            /* bit0 = 1st half, bit1 = 2nd */
static volatile uint32_t smp_tick_count;            /* ticks sampled since start */
static volatile uint32_t smp_half_start[2];         /* absolute first tick of each half */

/* SLP link state (protocol: Docs/20_Protocol/01_Protocol_SLP_v1.md) */
#define SLP_D1_BIT 2u /* D1 = PA2 -> bit 2 of GPIOA->IDR */
#define SLP_D2_BIT 3u /* D2 = PA3 -> bit 3 of GPIOA->IDR */
static slp_framer_t     slp_fr;
static slp_shell_t      slp_sh;
static volatile uint8_t slp_run;       /* 0 = STOP (default), 1 = streaming     */
static uint32_t         slp_tick_base; /* tick epoch: reset on every START      */
static uint32_t         slp_dropped;   /* DATA blocks dropped on USB backpressure */
static uint16_t         slp_cmd_err;   /* unknown commands received             */
static uint8_t          slp_data_frame[SLP_DATA_FRAME_LEN];
static uint8_t          slp_resp_frame[160];
static uint16_t         slp_resp_len;  /* 0 = nothing pending                   */
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_TIM3_Init(void);
static void MX_ADC1_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* Queue a response frame; if the previous one is still pending, the new one is
   dropped (commands are human-paced, this never happens in practice). */
static void slp_queue_response(uint8_t type, const char *json)
{
  if (slp_resp_len == 0u)
  {
    slp_resp_len = slp_build_frame(&slp_fr, slp_resp_frame, type,
                                   (const uint8_t *)json, (uint16_t)strlen(json));
  }
}

static void slp_handle_cmd(slp_cmd_t c)
{
  char js[96];

  switch (c)
  {
    case SLP_CMD_PING:
      slp_queue_response(SLP_TYPE_RESP, "{\"pong\":1}");
      break;

    case SLP_CMD_INFO:
      slp_queue_response(SLP_TYPE_RESP,
        "{\"fw\":\"0.1.0\",\"proto\":\"1.0\",\"mcu\":\"F103C6\","
        "\"rate\":10000,\"ch\":\"A2D2\",\"vref_mv\":3300}");
      break;

    case SLP_CMD_STAT:
      (void)snprintf(js, sizeof(js),
        "{\"run\":%u,\"tick\":%lu,\"dropped\":%lu,\"cmd_err\":%u}",
        (unsigned)slp_run,
        (unsigned long)(smp_tick_count - slp_tick_base),
        (unsigned long)slp_dropped,
        (unsigned)slp_cmd_err);
      slp_queue_response(SLP_TYPE_STAT, js);
      break;

    case SLP_CMD_START: /* new tick epoch, SEQ restarts (protocol §3) */
      slp_framer_reset(&slp_fr);
      slp_tick_base = smp_tick_count;
      smp_half_ready = 0u;
      slp_dropped = 0u;
      slp_run = 1u;
      slp_queue_response(SLP_TYPE_RESP, "{\"ok\":\"START\"}");
      break;

    case SLP_CMD_STOP:
      slp_run = 0u;
      slp_queue_response(SLP_TYPE_RESP, "{\"ok\":\"STOP\"}");
      break;

    default:
      slp_cmd_err++;
      slp_queue_response(SLP_TYPE_ERR, "{\"err\":\"unknown cmd\"}");
      break;
  }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  uint32_t led_ts = 0U;
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */
  /* Force USB re-enumeration: BluePill-style boards have a fixed D+ pull-up, so
     the host may latch a stale device state across resets. Pulling D+ (PA12) low
     for 50 ms makes the host see a disconnect and enumerate afresh. */
  {
    GPIO_InitTypeDef reenum = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    reenum.Pin = GPIO_PIN_12;
    reenum.Mode = GPIO_MODE_OUTPUT_PP;
    reenum.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &reenum);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);
    HAL_Delay(50);
    HAL_GPIO_DeInit(GPIOA, GPIO_PIN_12);
  }
  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_USB_DEVICE_Init();
  MX_TIM3_Init();
  MX_ADC1_Init();
  /* USER CODE BEGIN 2 */
  slp_framer_reset(&slp_fr);
  slp_shell_reset(&slp_sh);

  /* Start the free-running sampler. Order matters for phase alignment
     (Docs/30_Firmware/02): DMA channels first, ADC armed by TIM3 TRGO,
     the timer starts last so both streams begin on the same update event. */
  HAL_ADCEx_Calibration_Start(&hadc1);
  HAL_ADC_Start_DMA(&hadc1, (uint32_t *)adc_buf, 2u * SMP_HALF_TICKS * 2u);
  HAL_DMA_Start(&hdma_tim3_ch4_up, (uint32_t)&GPIOA->IDR, (uint32_t)gpio_buf,
                2u * SMP_HALF_TICKS);
  __HAL_TIM_ENABLE_DMA(&htim3, TIM_DMA_UPDATE);
  HAL_TIM_Base_Start(&htim3);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    /* LED heartbeat: 1 Hz idle, 5 Hz while streaming (30/01 LED policy). */
    if ((HAL_GetTick() - led_ts) >= (slp_run ? 100U : 500U))
    {
      led_ts = HAL_GetTick();
      HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
    }

    /* 1) push the pending response frame, if any (must not be lost) */
    if ((slp_resp_len > 0U) &&
        (CDC_Transmit_FS(slp_resp_frame, slp_resp_len) == USBD_OK))
    {
      slp_resp_len = 0U;
    }

    /* 2) feed incoming bytes to the command shell (CORE) */
    if (slp_resp_len == 0U)
    {
      uint8_t b;
      while (CDC_ReadRx(&b, 1U) == 1U)
      {
        slp_cmd_t c = slp_shell_feed(&slp_sh, b);
        if (c != SLP_CMD_NONE)
        {
          slp_handle_cmd(c);
          break;
        }
      }
    }

    /* 3) stream finished sampler halves as SLP DATA frames */
    if (slp_run != 0U)
    {
      for (uint8_t h = 0U; h < 2U; h++)
      {
        if ((smp_half_ready & (uint8_t)(1U << h)) != 0U)
        {
          uint32_t hs = smp_half_start[h];

          __disable_irq();
          smp_half_ready &= (uint8_t)~(1U << h);
          __enable_irq();

          /* skip a half that began before this epoch's START */
          if ((int32_t)(hs - slp_tick_base) >= 0)
          {
            uint16_t n = slp_build_data_frame(&slp_fr, slp_data_frame,
                                              hs - slp_tick_base,
                                              &adc_buf[(uint16_t)h * 64U],
                                              &gpio_buf[(uint16_t)h * 32U],
                                              SLP_D1_BIT, SLP_D2_BIT);
            if (CDC_Transmit_FS(slp_data_frame, n) != USBD_OK)
            {
              slp_dropped++; /* USB backpressure: drop whole block (NFR-02) */
            }
          }
        }
      }
    }
    else
    {
      smp_half_ready = 0U;
    }
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL6;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC|RCC_PERIPHCLK_USB;
  PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV4;
  PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_EXTERNALTRIGCONV_T3_TRGO;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 2;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_0;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_28CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_1;
  sConfig.Rank = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{

  /* USER CODE BEGIN TIM3_Init 0 */

  /* USER CODE END TIM3_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM3_Init 1 */

  /* USER CODE END TIM3_Init 1 */
  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 47;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 99;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_UPDATE;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM3_Init 2 */

  /* USER CODE END TIM3_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel1_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  /* DMA1_Channel3_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel3_IRQn, 15, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel3_IRQn);

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /*Configure GPIO pins : D1_IN_Pin D2_IN_Pin */
  GPIO_InitStruct.Pin = D1_IN_Pin|D2_IN_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */
  /* On-board LED PC13 (active low) is not configured in the .ioc - set it up
     here so the firmware has a visible "alive" indicator. */
  {
    GPIO_InitTypeDef led = {0};
    __HAL_RCC_GPIOC_CLK_ENABLE();
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET); /* LED off */
    led.Pin = GPIO_PIN_13;
    led.Mode = GPIO_MODE_OUTPUT_OD;
    led.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOC, &led);
  }
  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
/* Sampler DMA callbacks (ADC half/full transfer): record the half's first tick,
   advance the counter, flag the half - no heavy work in interrupt context. */
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance == ADC1)
  {
    smp_half_start[0] = smp_tick_count;
    smp_tick_count += SMP_HALF_TICKS;
    smp_half_ready |= 1u;
  }
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance == ADC1)
  {
    smp_half_start[1] = smp_tick_count;
    smp_tick_count += SMP_HALF_TICKS;
    smp_half_ready |= 2u;
  }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
