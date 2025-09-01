import M5
from M5 import *
from hardware import RGB, I2C, Pin
import requests2
import network
import time
import ubluetooth
from unit import ENVUnit
import machine

SUPABASE_URL = 'https://odabslohlhkklziizpeh.supabase.co/rest/v1'
API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'
SERVICE_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
CHAR_UUID = ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E')
READING_INTERVAL = 600000  # 10 minute

wlan = network.WLAN(network.STA_IF)
rgb = RGB()
env_sensor = None
ble = None
mac_address = ''.join('{:02X}'.format(b) for b in wlan.config('mac'))
is_registered = False
is_pairing = False
ble_initialized = False
last_reading = 0
last_check = 0
char_handle = None
connections = set()
has_error = False

def ensure_wifi_connection():
    """Ensure WiFi is connected before API calls"""
    if not wlan.isconnected():
        print('WiFi not connected, attempting to connect...')
        wlan.active(True)
        timeout = 10
        while timeout > 0 and not wlan.isconnected():
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            print(f'WiFi connected: {wlan.ifconfig()}')
            return True
        else:
            print('WiFi connection failed')
            return False
    return True

def api_call(method, endpoint, data=None):
    """Make API call with error handling"""
    if not ensure_wifi_connection():
        print('No WiFi connection for API call')
        return None, None
        
    try:
        url = f'{SUPABASE_URL}/{endpoint}'
        headers = {'apikey': API_KEY}
        if data:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        response = getattr(requests2, method.lower())(url, data=data, headers=headers) if data else getattr(requests2, method.lower())(url, headers=headers)
        result = response.status_code, response.json() if method == 'GET' else None
        response.close()
        return result
    except Exception as e:
        print(f'API error: {e}')
        return None, None

def ble_irq(event, data):
    """Handle BLE events"""
    global is_registered, is_pairing, last_reading, ble_initialized
    if not ble or not ble_initialized:
        return
        
    if event == 1:  # Connect
        conn_handle = data[0]
        connections.add(conn_handle)
        print(f'BLE connected: {conn_handle}')
    elif event == 2:  # Disconnect
        connections.discard(data[0])
        start_advertising()
    elif event == 3:  # Write
        conn_handle, value_handle = data
        try:
            value = ble.gatts_read(value_handle)
        except Exception as e:
            print(f'GATT read error: {e}')
            return
        if value == b'GET_READINGS' and env_sensor:
            readings = f'{{"temp":{env_sensor.read_temperature()},"humidity":{env_sensor.read_humidity()},"pressure":{env_sensor.read_pressure()}}}'
            try:
                if ble and ble_initialized and char_handle:
                    ble.gatts_notify(conn_handle, char_handle, readings.encode())
            except Exception as e:
                print(f'Notify error: {e}')
        elif value == b'REGISTER':
            status, _ = api_call('POST', 'devices', requests2.urlencode({
                'mac_address': mac_address,
                'name': f'NanoC6-{mac_address[-6:]}',
                'connected_at': time.time()
            }))
            if status == 201:
                is_registered = True
                is_pairing = False
                rgb.fill_color(0x000000)
                last_reading = time.ticks_ms() - READING_INTERVAL
                print('Device registered - immediate reading scheduled')
                has_error = False
                try:
                    if ble and ble_initialized and char_handle:
                        ble.gatts_notify(conn_handle, char_handle, b'REGISTERED')
                        # Wait a moment for the notification to be sent
                        time.sleep(1)
                except Exception as e:
                    print(f'Registration notify error: {e}')
                # Disable BLE after successful registration and notification
                disable_ble()
            else:
                print(f'Registration failed: {status}')
                has_error = True
                try:
                    if ble and ble_initialized and char_handle:
                        ble.gatts_notify(conn_handle, char_handle, b'REGISTER_FAILED')
                except Exception as e:
                    print(f'Registration failed notify error: {e}')

def start_advertising():
    """Start BLE advertising"""
    if not ble:
        return
    name = f'NanoC6-{mac_address[-6:]}'
    adv_data = bytes([0x02, 0x01, 0x06, 0x02, 0x0A, 0x1A, len(name) + 1, 0x09]) + name.encode()
    try:
        ble.gap_advertise(500000, adv_data=adv_data, connectable=True)
    except:
        pass

def disable_ble():
    """Disable BLE to save power"""
    global ble, ble_initialized, connections, char_handle
    if ble and ble_initialized:
        try:
            # Disconnect all active connections first
            for conn in list(connections):
                try:
                    ble.gap_disconnect(conn)
                except:
                    pass
            connections.clear()
            
            # Stop advertising and deactivate
            ble.gap_advertise(None)
            ble.active(False)
            ble_initialized = False
            char_handle = None
            print('BLE disabled and connections cleared')
        except Exception as e:
            print(f'BLE disable error: {e}')
            # Force reset state even if disable fails
            ble_initialized = False
            char_handle = None
            connections.clear()

def init_ble():
    """Initialize BLE"""
    global char_handle, ble, ble_initialized
    try:
        if not ble:
            ble = ubluetooth.BLE()
        ble.active(True)
        ble.irq(ble_irq)
        services = ((SERVICE_UUID, ((CHAR_UUID, 0x001A),)),)
        ((char_handle,),) = ble.gatts_register_services(services)
        ble.gatts_write(char_handle, b'Ready')
        start_advertising()
        ble_initialized = True
        return True
    except Exception as e:
        print(f'BLE init error: {e}')
        return False

def check_registration():
    """Check device registration status"""
    global is_registered, last_check, has_error
    status, data = api_call('GET', f'devices?mac_address=eq.{mac_address}&select=id')
    if status == 200:
        was_registered = is_registered
        is_registered = bool(data and len(data) > 0)
        if is_registered != was_registered and not has_error:
            rgb.fill_color(0x000000)
    else:
        has_error = True
    last_check = time.ticks_ms()

def take_reading():
    """Take sensor reading and send to cloud"""
    global last_reading, has_error
    if not env_sensor:
        return
    try:
        temp = env_sensor.read_temperature()
        humidity = env_sensor.read_humidity()
        pressure = env_sensor.read_pressure()
        
        status, _ = api_call('POST', 'readings', requests2.urlencode({
            'mac_address': mac_address,
            'temperature': temp,
            'humidity': humidity,
            'pressure': pressure,
            'sensor': 'm5_env_4'
        }))
        
        if status and str(status)[0] == '2':
            print(f'Reading sent: {temp}°C, {humidity}%, {pressure}hPa')
            # Flash green for successful upload
            rgb.fill_color(0x00ff00)
            time.sleep(1)
            rgb.fill_color(0x000000)
            has_error = False
        else:
            has_error = True
        last_reading = time.ticks_ms()
    except Exception as e:
        print(f'Reading error: {e}')
        has_error = True

def btn_hold_event(state):
    """Handle button hold - start pairing"""
    global is_pairing
    if is_registered:
        print('Device already registered - pairing not needed')
        # Flash white to indicate already registered
        rgb.fill_color(0xffffff)
        time.sleep(0.5)
        rgb.fill_color(0x000000)
        return
        
    if not is_pairing:
        is_pairing = True
        rgb.fill_color(0x0000ff)
        print('Pairing mode started - enabling Bluetooth')
        if init_ble():
            print('BLE initialized successfully')
        else:
            print('BLE initialization failed')
            is_pairing = False
            has_error = True

def setup():
    """Initialize hardware"""
    global env_sensor
    M5.begin()
    BtnA.setCallback(type=BtnA.CB_TYPE.WAS_HOLD, cb=btn_hold_event)
    
    rgb.set_brightness(10)
    rgb.fill_color(0x000000)
    
    wlan.active(True)
    print(f'WiFi status: {"Connected" if wlan.isconnected() else "Disconnected"}')
    if wlan.isconnected():
        print(f'WiFi IP: {wlan.ifconfig()[0]}')
    
    try:
        i2c = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
        env_sensor = ENVUnit(i2c=i2c, type=4)
        print('Sensor initialized')
    except Exception as e:
        print(f'Sensor init failed: {e}')
    
    print(f'MAC: {mac_address}')
    
    # Check registration status without initializing BLE
    check_registration()
    if is_registered:
        print('Device already registered - BLE will remain disabled')
        last_reading = time.ticks_ms() - READING_INTERVAL  # Force immediate reading
        # Ensure BLE is completely disabled for registered devices
        if ble_initialized:
            disable_ble()

def loop():
    """Main loop"""
    global is_pairing
    M5.update()
    current_time = time.ticks_ms()
    
    if is_pairing:
        rgb.fill_color(0x0000ff)
        time.sleep_ms(100)
        return
    
    # Handle error state - stay red
    if has_error:
        rgb.fill_color(0xff0000)
        time.sleep_ms(100)
        return
    
    check_interval = 10000 if not is_registered else 300000
    if time.ticks_diff(current_time, last_check) > check_interval:
        check_registration()
        # Ensure BLE is disabled if device becomes registered
        if is_registered and ble_initialized:
            disable_ble()
    
    if not is_registered:
        rgb.fill_color(0xffffff)
    else:
        rgb.fill_color(0x000000)
        # Ensure BLE stays disabled for registered devices
        if ble_initialized:
            disable_ble()
        if time.ticks_diff(current_time, last_reading) >= READING_INTERVAL:
            take_reading()
    
    time.sleep_ms(100)

# Main execution
if __name__ == '__main__':
    try:
        setup()
        while True:
            try:
                loop()
            except Exception as e:
                print(f'Loop error: {e}')
                has_error = True
    except Exception as e:
        print(f'Fatal error: {e}')
        rgb.fill_color(0xff0000)
        for _ in range(3):
            time.sleep(0.2)
            rgb.fill_color(0x000000)
            time.sleep(0.2)
            rgb.fill_color(0xff0000)
        machine.reset()
