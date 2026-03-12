import network
import urequests
import ubinascii
import time
from machine import ADC, Pin, I2C
import dht
import ssd1306
import framebuf

button = Pin(14, Pin.IN, Pin.PULL_UP)
display_mode = 0
last_button = 1
last_press_time = 0

i2c = I2C(0, scl=Pin(25), sda=Pin(26))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

def text_big(oled, text, x, y, scale=4, color=1):
    x_compress = 0.66
    for char in text:
        buf = bytearray(8 * 8 // 8)
        fb = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_HLSB)
        fb.fill(0)
        fb.text(char, 0, 0, 1)
        for cy in range(8):
            for cx in range(8):
                if fb.pixel(cx, cy):
                    for dy in range(scale):
                        for dx in range(scale):
                            px = int(x + (cx * scale + dx) * x_compress)
                            py = y + (cy * scale + dy)
                            if 0 <= px < 128 and 0 <= py < 64:
                                oled.pixel(px, py, color)
        x += int(8 * scale * x_compress) + 2

frame = 0

def ticker(text):
    global frame
    char_w = int(8 * 4 * 0.66)
    width = len(text) * (char_w + 3)
    for offset in range(128, -width, -6):
        check_button()
        if display_mode != 0:
            return
        oled.fill(0)
        text_big(oled, text, offset, 10, scale=4)
        oled.show()
        frame += 1
        if frame % 30 == 0:
            send_metrics(last_temp, last_humid, last_light_raw, last_soil)

WIFI_1 = "WIFI 1"
PASS_1 = "PASS"
WIFI_2 = "WIFI 2"
PASS_2 = "PASS"

GC_URL = "INFLUX DB URL HERE"
GC_USER = "USER ID HERE (garafana)"
GC_TOKEN = "API KEY HERE"

light_adc = ADC(Pin(34))
light_adc.atten(ADC.ATTN_11DB)
dht_sensor = dht.DHT11(Pin(13))
soil_adc = ADC(Pin(32))
soil_adc.atten(ADC.ATTN_11DB)

SOIL_DRY = 3300
SOIL_WET = 1100

def read_light():
    return round(light_adc.read() / 4095 * 100, 1)

def read_dht():
    for _ in range(3):
        try:
            time.sleep(0.5)
            dht_sensor.measure()
            return dht_sensor.temperature(), dht_sensor.humidity()
        except:
            time.sleep(0.1)
    return 0, 0

def read_soil():
    raw = soil_adc.read()
    pct = (SOIL_DRY - raw) / (SOIL_DRY - SOIL_WET) * 100
    return max(0, min(100, round(pct, 1)))

def send_metrics(temp, humid, light_raw, soil):
    creds = "{}:{}".format(GC_USER, GC_TOKEN)
    encoded = ubinascii.b2a_base64(creds.encode()).decode().strip()
    headers = {"Content-Type": "text/plain", "Authorization": "Basic " + encoded}
    body = "plant_sensors,device=esp32,location=indoor temperature={:.1f},humidity={:.1f},light={:.1f},soil_moisture={:.1f}".format(temp, humid, light_raw, soil)
    try:
        r = urequests.post(GC_URL, data=body, headers=headers)
        print("Sent", r.status_code)
        r.close()
    except Exception as e:
        print("UPLOAD ERROR:", e)

def splash_screen():
    oled.fill(0)
    text_big(oled, "SAI TECH", -2, 5, scale=3)
    text_big(oled, "SYSTEMS", -2, 35, scale=2)
    oled.show()
    time.sleep(1)
    oled.fill(0)
    oled.show()

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(0.5)
    splash_screen()
    for ssid, password in [(WIFI_1, PASS_1), (WIFI_2, PASS_2)]:
        wlan.disconnect()
        wlan.active(False)
        time.sleep(0.5)
        wlan.active(True)
        time.sleep(0.5)
        wlan.connect(ssid, password)
        timeout = 30
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.2)
            timeout -= 1
        if wlan.isconnected():
            oled.fill(0)
            text_big(oled, "Connected!", 0, 0, scale=2)
            oled.show()
            time.sleep(1)
            oled.fill(0)
            return True
    oled.fill(0)
    text_big(oled, "NO WIFI", 0, 0, scale=2)
    text_big(oled, "OFFLINE", 0, 25, scale=2)
    oled.show()
    time.sleep(1)
    oled.fill(0)
    return False

def show_page_mode(page, temp_f, humid, light_display, soil):
    oled.fill(0)
    if page == 0:
        text_big(oled, "TEMP", 0, 0, scale=3)
        text_big(oled, "{}F".format(int(temp_f)), 0, 30, scale=4)
    elif page == 1:
        text_big(oled, "HUMIDITY", 0, 0, scale=2)
        text_big(oled, "{}%".format(int(humid)), 0, 30, scale=3)
    elif page == 2:
        text_big(oled, "LIGHT", 0, 0, scale=3)
        text_big(oled, light_display, 0, 30, scale=4)
    elif page == 3:
        text_big(oled, "SOIL", 0, 0, scale=3)
        text_big(oled, "{}%".format(int(soil)), 0, 30, scale=4)
    oled.show()

def show_one_page(temp_f, humid, light_display, soil):
    oled.fill(0)
    text_big(oled, "T:{}F".format(int(temp_f)), 0, 0, scale=2)
    text_big(oled, "H:{}%".format(int(humid)), 70, 0, scale=2)
    text_big(oled, "S:{}%".format(int(soil)), 0, 30, scale=2)
    text_big(oled, "L:{}".format(light_display), 60, 30, scale=2)
    oled.show()

def check_button():
    global last_button, last_press_time, display_mode
    reading = button.value()
    if reading == 0 and last_button == 1:
        now = time.ticks_ms()
        if now - last_press_time > 300:
            display_mode = (display_mode + 1) % 3
            oled.fill(0)
            if display_mode == 0:
                text_big(oled, "SCROLL", 0, 10, scale=3)
            elif display_mode == 1:
                text_big(oled, "PAGE", 0, 10, scale=3)
            else:
                text_big(oled, "1 PAGE", 0, 10, scale=3)
            oled.show()
            time.sleep(1)
            oled.fill(0)
            last_press_time = now
    last_button = reading

wifi_ok = connect_wifi()
time.sleep(1)

page = 0
last_page_switch = time.time()

last_temp = 0
last_humid = 0
last_light_raw = 0
last_soil = 0

while True:
    check_button()
    last_light_raw = read_light()
    last_temp, last_humid = read_dht()
    last_soil = read_soil()
    temp_f = last_temp * 9/5 + 32
    light_display = "GOOD" if last_light_raw < 50 else "LOW"
    ticker_text = "TEMP {}F | HUM {}% | SOIL {}% | LIGHT {} |".format(int(temp_f), int(last_humid), int(last_soil), light_display)

    if display_mode == 0:
        ticker(ticker_text)
    else:
        send_metrics(last_temp, last_humid, last_light_raw, last_soil)
        if display_mode == 1:
            if time.time() - last_page_switch > 2:
                page = (page + 1) % 4
                last_page_switch = time.time()
            show_page_mode(page, temp_f, last_humid, light_display, last_soil)
        else:
            show_one_page(temp_f, last_humid, light_display, last_soil)

