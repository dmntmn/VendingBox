# Серверное ПО управляющего компьютера — описание и алгоритм

## Назначение

Программа является центральным управляющим ПО вендингового аппарата.
Запускается на x86-компьютере под Windows 10 IoT или Linux.
Координирует все подсистемы: сателлиты (ATmega328 по RS-485), купюроприёмник (CC-Net),
картридер (MDB), экран (PyQt6).

---

## Стек технологий

| Компонент        | Технология                        |
|------------------|-----------------------------------|
| Язык             | Python 3.11+                      |
| Асинхронность    | asyncio + asyncio.Queue           |
| COM-порты        | pyserial-asyncio                  |
| UI               | PyQt6 + QMediaPlayer              |
| БД               | SQLite (stdlib sqlite3)           |
| Конфигурация     | JSON                              |
| Совместный loop  | qasync (asyncio + PyQt6)          |

---

## Архитектура

Приложение построено на трёх слоях:

```
┌─────────────────────────────────────────────┐
│                   UI (PyQt6)                │  ← отображение, реклама, экраны
├─────────────────────────────────────────────┤
│              FSM (конечный автомат)         │  ← бизнес-логика, состояния
├──────────────┬──────────────┬───────────────┤
│ driver_rs485 │ driver_ccnet │  driver_mdb   │  ← драйверы железа
└──────────────┴──────────────┴───────────────┘
```

Все драйверы работают как asyncio-корутины и общаются с FSM через две очереди:
- `Q_IN`  — события от железа → FSM
- `Q_UI`  — команды от FSM → UI

---

## Алгоритм работы

### 1. Запуск приложения

```
1. Загрузить config.json (товары, цены, COM-порты, таймауты)
2. Инициализировать SQLite БД (создать таблицы если нет)
3. Открыть COM-порты: RS-485, CC-Net, MDB
4. Запустить asyncio-корутины: driver_rs485, driver_ccnet, driver_mdb
5. Запустить корутину FSM
6. Показать экран рекламы (IDLE)
```

---

### 2. Основной цикл FSM

FSM ждёт события из Q_IN и переключает состояния:

```
IDLE
 │
 ├─ [rs485: BUTTON_PRESSED addr=N]
 │     → сохранить выбранный товар N
 │     → Q_UI: показать экран цены товара N
 │     → включить CC-Net (ENABLE)
 │     → включить MDB (SETUP + POLL)
 │     → запустить таймер 30 сек
 │     → перейти в ITEM_SELECTED
 │
ITEM_SELECTED
 │
 ├─ [rs485: BUTTON_PRESSED addr=M]  (смена товара)
 │     → обновить выбранный товар M
 │     → Q_UI: обновить экран цены
 │     → сбросить таймер
 │
 ├─ [таймаут 30 сек]
 │     → отключить CC-Net, MDB
 │     → Q_UI: вернуть экран рекламы
 │     → перейти в IDLE
 │
 ├─ [ccnet: BILL_ESCROW amount=X]
 │     → если X >= цена товара → STACK (принять купюру)
 │     → иначе → RETURN (вернуть купюру)
 │
 ├─ [ccnet: BILL_STACKED amount=X]
 │     → накопленная сумма += X
 │     → если сумма >= цена → перейти в DISPENSING
 │
 ├─ [mdb: SESSION_BEGIN]
 │     → отправить VEND REQUEST [сумма товара]
 │
 ├─ [mdb: VEND_APPROVED]
 │     → перейти в DISPENSING
 │
DISPENSING
 │
 ├─ отправить rs485: MOTOR_START [addr=N, dir=config]
 │  → Q_UI: показать экран «Выдача товара...»
 │  → запустить таймер выдачи (dispense_sec из config)
 │
 ├─ [rs485: DISPENSE_OK addr=N]
 │     → перейти в SUCCESS
 │
 ├─ [rs485: DISPENSE_TIMEOUT addr=N]  или  [таймаут dispense_sec]
 │     → перейти в ERROR
 │
SUCCESS
 │
 ├─ записать транзакцию в SQLite
 ├─ MDB: VEND SUCCESS → SESSION COMPLETE
 ├─ CC-Net: отключить приём
 ├─ Q_UI: показать «Заберите товар» (success_screen_sec)
 └─ перейти в IDLE
 │
ERROR
 │
 ├─ MDB: VEND FAILURE → SESSION COMPLETE
 ├─ CC-Net: вернуть деньги (RETURN накопленной суммы)
 ├─ записать ошибку в SQLite
 ├─ Q_UI: показать экран ошибки
 └─ перейти в IDLE
```

---

### 3. Алгоритм драйвера RS-485

```
1. Открыть COM-порт (115200 baud, 8N1)
2. Бесконечный цикл опроса addr = 1..32:
   a. Сформировать пакет GET_STATUS [ADDR][0x02][CRC16]
   b. Отправить пакет (DE=HIGH → байты → DE=LOW)
   c. Ждать ответ с таймаутом 10 мс
   d. Если нет ответа → счётчик ошибок addr++, continue
   e. Проверить CRC16 ответа
   f. Разобрать FLAGS байт:
      - бит 2 (кнопка) → Q_IN.put(BUTTON_PRESSED, addr)
      - бит 1 (детектор) → Q_IN.put(DISPENSE_OK, addr)
   g. Если FSM ждёт результат выдачи для addr:
      - опросить DISPENSE_RESULT [0x05]
      - положить результат в Q_IN
   h. addr++
3. Команды от FSM (MOTOR_START, MOTOR_STOP) принимать
   через отдельную asyncio.Queue и вставлять в цикл опроса
```

---

### 4. Алгоритм драйвера CC-Net

```
1. Открыть COM-порт (9600 baud, 8N1)
2. По умолчанию — устройство DISABLED
3. При команде ENABLE от FSM:
   a. Отправить ENABLE команду купюроприёмнику
   b. Войти в цикл опроса (POLL каждые 200 мс)
   c. При получении ESCROW → положить в Q_IN
   d. При получении STACKED → положить в Q_IN
   e. При получении RETURNED → положить в Q_IN
4. При команде DISABLE от FSM:
   a. Отправить DISABLE купюроприёмнику
   b. Выйти из цикла опроса
```

---

### 5. Алгоритм драйвера MDB

```
1. Открыть COM-порт (9600 baud, 9-bit)
2. Отправить RESET → дождаться JUST RESET
3. Отправить SETUP → получить конфигурацию устройства
4. По умолчанию — ожидание (POLL без активной сессии)
5. При команде SETUP+POLL от FSM:
   a. Войти в активный режим опроса (POLL каждые 100 мс)
   b. При BEGIN SESSION → положить в Q_IN
6. При команде VEND REQUEST [сумма] от FSM:
   a. Отправить VEND REQUEST
   b. Ждать VEND APPROVED / VEND DENIED
   c. Положить результат в Q_IN
7. При команде VEND SUCCESS / VEND FAILURE от FSM:
   a. Отправить соответствующую команду
   b. Отправить SESSION COMPLETE
```

---

### 6. Алгоритм UI (PyQt6)

```
1. Запустить главное окно в полноэкранном режиме
2. Слушать Q_UI в отдельном потоке (через QTimer или qasync)
3. Команды Q_UI:
   - SHOW_IDLE      → запустить слайдшоу media/
   - SHOW_PRICE N   → показать фото, название, цену товара N
   - SHOW_DISPENSE  → показать анимацию выдачи
   - SHOW_SUCCESS   → показать «Заберите товар»
   - SHOW_ERROR     → показать экран ошибки
   - UPDATE_AMOUNT X → обновить индикатор принятой суммы
```

---

## Формат событий в Q_IN

```python
{
    "source": "rs485" | "ccnet" | "mdb",
    "event":  str,       # имя события
    "data":   dict       # полезная нагрузка
}
```

| source  | event              | data                  |
|---------|--------------------|-----------------------|
| rs485   | BUTTON_PRESSED     | {"addr": N}           |
| rs485   | DISPENSE_OK        | {"addr": N}           |
| rs485   | DISPENSE_TIMEOUT   | {"addr": N}           |
| ccnet   | BILL_ESCROW        | {"amount": X}         |
| ccnet   | BILL_STACKED       | {"amount": X}         |
| ccnet   | BILL_RETURNED      | {}                    |
| mdb     | SESSION_BEGIN      | {}                    |
| mdb     | VEND_APPROVED      | {"amount": X}         |
| mdb     | VEND_DENIED        | {}                    |

---

## Состояния FSM

| Состояние      | Описание                                      |
|----------------|-----------------------------------------------|
| IDLE           | Реклама, все платёжные устройства отключены   |
| ITEM_SELECTED  | Товар выбран, ожидание оплаты, таймер 30 сек  |
| DISPENSING     | Мотор запущен, ожидание детектора             |
| SUCCESS        | Товар выдан, запись транзакции                |
| ERROR          | Ошибка выдачи, возврат денег                  |

---

## Схема файлов проекта

```
vending_pc/
├── DESCRIPTION.md           ← этот файл
├── main.py                  ← точка входа
├── requirements.txt         ← зависимости
├── config.json              ← товары, цены, порты, таймауты
│
├── core/
│   ├── __init__.py
│   ├── fsm.py               ← конечный автомат
│   ├── db.py                ← SQLite: транзакции, логи
│   └── config_loader.py     ← загрузка и валидация config.json
│
├── drivers/
│   ├── __init__.py
│   ├── driver_rs485.py      ← опрос 32 сателлитов ATmega328
│   ├── driver_ccnet.py      ← купюроприёмник CC-Net
│   └── driver_mdb.py        ← картридер MDB
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py       ← главное окно PyQt6
│   ├── screen_idle.py       ← экран рекламы (слайдшоу)
│   ├── screen_price.py      ← экран выбора товара и оплаты
│   └── screen_dispense.py   ← экран выдачи / ошибки
│
└── media/
    └── .gitkeep             ← изображения и видео товаров
```
