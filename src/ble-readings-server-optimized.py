import os, sys, io
import M5
from M5 import *
from hardware import RGB
import requests2
import network
import time
import ubluetooth
from unit import ENVUnit
from hardware import I2C, Pin
import ubinascii
import machine

# Configuration Constants
class Config:
    # BLE Configuration
    SERVICE_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
    CHAR_UUID = ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E')
    FLAG_READ = 0x0002
    FLAG_WRITE = 0x0008
    FLAG_NOTIFY = 0x0010
    
    # API Configuration
    SUPABASE_URL = 'https://odabslohlhkklziizpeh.supabase.co/rest/v1'
    API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'
    
    # Timing Configuration
    READING_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes
    REGISTRATION_CHECK_INTERVAL = 10000   # 10 seconds when unregistered
    REGISTRATION_CHECK_INTERVAL_REGISTERED = 300000  # 5 minutes when registered
    PAIRING_TIMEOUT = 120000  # 2 minutes
    
    # LED Colors
    LED_OFF = 0x000000
    LED_WHITE = 0xffffff  # Unregistered
    LED_BLUE = 0x0000ff   # Pairing
    LED_RED = 0xff0000    # Error

# Global state
class State:
    def __init__(self):
        self.wlan = None
        self.rgb = None
        self.i2c0 = None
        self.env4_0 = None
        self.ble_server = None
        self.mac_address = None
        self.is_pairing = False
        self.is_registered = False
        self.last_reading_time = 0
        self.last_registration_check = 0
        self.force_immediate_reading = False

state = State()

# Utility Functions
def safe_execute(func, error_msg, default_return=False):
    """Execute function with error handling"""
    try:
        return func()
    except Exception as e:
        print(f'{error_msg}: {e}')
        return default_return

def get_device_name():
    """Generate device name from MAC address"""
    return f'NanoC6-{state.mac_address[-6:] if state.mac_address else "UNKNOWN"}'

def create_ble_advertising_data(name):
    """Create BLE advertising data"""
    adv_data = bytearray([
        0x02, 0x01, 0x06,  # Flags
        0x02, 0x0A, 0x1A,  # 16-bit Service UUID
        len(name) + 1, 0x09  # Complete local name
    ])
    adv_data.extend(name.encode('utf-8'))
    return bytes(adv_data)

def make_api_request(method, endpoint, data=None, json_data=None):
    """Make API request with proper error handling"""
    url = f'{Config.SUPABASE_URL}/{endpoint}'
    headers = {'apikey': Config.API_KEY}
    
    if json_data:
        headers['Content-Type'] = 'application/json'
        headers['Prefer'] = 'return=representation'
    elif data:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    response = None
    try:
        if method == 'GET':
            response = requests2.get(url, headers=headers)
        elif method == 'POST':
            if json_data:
                response = requests2.post(url, json=json_data, headers=headers)
            else:
                response = requests2.post(url, data=data, headers=headers)
        return response
    except Exception as e:
        print(f'API request error: {e}')
        if response:
            response.close()
        return None

class BLEReadingsServer:
    def __init__(self):
        self.ble = ubluetooth.BLE()
        self.connections = set()
        self._char_handle = None
        self._init_ble()
        
    def _init_ble(self):
        """Initialize BLE with error handling"""
        def init():
            self.ble.active(True)
            self.ble.irq(self._ble_irq)
            
            # Register service
            services = ((Config.SERVICE_UUID, 
                        ((Config.CHAR_UUID, Config.FLAG_READ | Config.FLAG_WRITE | Config.FLAG_NOTIFY),)),)
            ((self._char_handle,),) = self.ble.gatts_register_services(services)
            
            self.ble.gatts_write(self._char_handle, 'Ready')
            self._advertise()
            print('BLE services registered')
            return True
            
        if not safe_execute(init, "Failed to initialize BLE"):
            machine.reset()
    
    def _advertise(self):
        """Start BLE advertising"""
        name = get_device_name()
        adv_data = create_ble_advertising_data(name)
        
        def advertise():
            self.ble.gap_advertise(500000, adv_data=adv_data, connectable=True)
            print(f'Advertising as {name}...')
            return True
            
        if not safe_execute(advertise, "Failed to start advertising"):
            machine.reset()
    
    def _ble_irq(self, event, data):
        """Handle BLE events"""
        if event == 1:  # Connect
            conn_handle, _, _ = data
            self.connections.add(conn_handle)
            print(f'Connected: {conn_handle}')
            
        elif event == 2:  # Disconnect
            conn_handle, _, _ = data
            self.connections.discard(conn_handle)
            print(f'Disconnected: {conn_handle}')
            self._advertise()
            
        elif event == 3:  # Write
            conn_handle, value_handle = data
            if value_handle == self._char_handle:
                value = self.ble.gatts_read(value_handle)
                self._handle_command(value, conn_handle)
    
    def _handle_command(self, command, conn_handle):
        """Handle BLE commands"""
        try:
            if command == b'GET_READINGS':
                self._send_readings()
            elif command == b'REGISTER':
                self._handle_registration()
            else:
                self.ble.gatts_write(self._char_handle, command)
        except Exception as e:
            print(f'Error handling BLE command: {e}')
    
    def _send_readings(self):
        """Send sensor readings via BLE"""
        if not self.connections or not state.env4_0:
            return
            
        try:
            readings = {
                'temperature': state.env4_0.read_temperature(),
                'humidity': state.env4_0.read_humidity(),
                'pressure': state.env4_0.read_pressure(),
                'timestamp': time.time()
            }
            
            for conn_handle in self.connections:
                safe_execute(
                    lambda: self.ble.gatts_write(self._char_handle, str(readings).encode()),
                    "Error sending readings"
                )
        except Exception as e:
            print(f"Error reading sensors: {e}")
    
    def _handle_registration(self):
        """Handle device registration via BLE"""
        success = register_device()
        response = b'REGISTERED' if success else b'REGISTER_FAILED'
        safe_execute(
            lambda: self.ble.gatts_write(self._char_handle, response),
            "Registration response error"
        )

def check_device_registered():
    """Check if device is registered"""
    print('Checking if device is registered...')
    
    response = make_api_request('GET', f'devices?mac_address=eq.{state.mac_address}&select=id')
    
    if response and response.status_code == 200:
        data = response.json()
        was_registered = state.is_registered
        state.is_registered = bool(data and len(data) > 0)
        
        # Update LED only on state change
        if state.is_registered != was_registered:
            color = Config.LED_OFF if state.is_registered else Config.LED_WHITE
            state.rgb.fill_color(color)
            
        print('Device is registered' if state.is_registered else 'Device is not registered')
    else:
        print('Error checking registration status')
    
    if response:
        response.close()
    state.last_registration_check = time.ticks_ms()

def register_device():
    """Register device with API"""
    print('Registering device...')
    
    response = make_api_request('POST', 'devices', json_data={
        'mac_address': state.mac_address,
        'name': get_device_name(),
        'connected_at': time.time()
    })
    
    success = response and response.status_code == 201
    if success:
        print('Device registered successfully')
        state.is_registered = True
        state.rgb.fill_color(Config.LED_OFF)
        state.force_immediate_reading = True
    else:
        print('Failed to register device')
    
    if response:
        response.close()
    return success

def take_readings():
    """Take sensor readings and send to cloud"""
    if not state.env4_0:
        return False
        
    print('Taking readings...')
    
    try:
        # Read sensors
        temp = state.env4_0.read_temperature()
        humidity = state.env4_0.read_humidity()
        pressure = state.env4_0.read_pressure()
        
        print(f'Temperature: {temp}°C, Humidity: {humidity}%, Pressure: {pressure}hPa')
        
        # Send to cloud
        response = make_api_request('POST', 'readings', data=requests2.urlencode({
            'mac_address': state.mac_address,
            'temperature': temp,
            'humidity': humidity,
            'pressure': pressure,
            'sensor': 'm5_env_4'
        }))
        
        success = response and str(response.status_code)[0] == '2'
        if success:
            print('Readings sent to cloud!')
        else:
            print('Failed to send readings to cloud')
            
        if response:
            response.close()
        return success
        
    except Exception as e:
        print(f'Error in take_readings: {e}')
        return False

def reading_cycle():
    """Handle reading cycle with timing control"""
    current_time = time.ticks_ms()
    
    # Check if we should take a reading
    if not state.force_immediate_reading:
        if time.ticks_diff(current_time, state.last_reading_time) < Config.READING_INTERVAL_MS:
            return
    
    print('Starting reading cycle...')
    state.last_reading_time = current_time
    state.force_immediate_reading = False
    
    take_readings()
    print('Reading cycle complete')

def start_pairing_mode():
    """Start BLE pairing mode"""
    print('Starting BLE pairing mode...')
    state.rgb.fill_color(Config.LED_BLUE)
    state.is_pairing = True
    
    # Use the existing BLE server for pairing
    if not state.ble_server:
        state.ble_server = BLEReadingsServer()
    
    # Wait for registration or timeout
    start_time = time.ticks_ms()
    while state.is_pairing and time.ticks_diff(time.ticks_ms(), start_time) < Config.PAIRING_TIMEOUT:
        time.sleep_ms(100)
        if state.is_registered:
            break
    
    state.is_pairing = False
    state.rgb.fill_color(Config.LED_OFF)
    print('Exited BLE pairing mode')
    
    if state.is_registered:
        reading_cycle()

def btnA_wasHold_event(state_param):
    """Handle button hold event"""
    if not state.is_pairing and not state.is_registered:
        start_pairing_mode()

def setup():
    """Initialize hardware and check registration"""
    M5.begin()
    BtnA.setCallback(type=BtnA.CB_TYPE.WAS_HOLD, cb=btnA_wasHold_event)
    
    # Initialize hardware
    state.wlan = network.WLAN(network.STA_IF)
    state.rgb = RGB()
    state.rgb.set_brightness(10)
    state.rgb.fill_color(Config.LED_OFF)
    
    # Initialize I2C and sensor
    def init_sensor():
        state.i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
        state.env4_0 = ENVUnit(i2c=state.i2c0, type=4)
        return True
        
    safe_execute(init_sensor, "Failed to initialize I2C or ENV sensor")
    
    # Get MAC address
    mac_bytes = state.wlan.config('mac')
    state.mac_address = ''.join('{:02X}'.format(b) for b in mac_bytes)
    print(f'MAC Address: {state.mac_address}')
    
    # Check registration status
    check_device_registered()
    
    # Initialize BLE server
    state.ble_server = BLEReadingsServer()
    
    if state.is_registered:
        state.force_immediate_reading = True

def loop():
    """Main loop"""
    M5.update()
    
    if state.is_pairing:
        state.rgb.fill_color(Config.LED_BLUE)
        time.sleep_ms(100)
        return
    
    current_time = time.ticks_ms()
    
    # Check registration periodically
    check_interval = (Config.REGISTRATION_CHECK_INTERVAL if not state.is_registered 
                     else Config.REGISTRATION_CHECK_INTERVAL_REGISTERED)
    
    if time.ticks_diff(current_time, state.last_registration_check) > check_interval:
        check_device_registered()
    
    if not state.is_registered:
        state.rgb.fill_color(Config.LED_WHITE)
    else:
        state.rgb.fill_color(Config.LED_OFF)
        reading_cycle()
    
    time.sleep_ms(100)

def main():
    """Main function with error handling"""
    try:
        setup()
        while True:
            try:
                loop()
            except Exception as e:
                print(f'Error in main loop: {e}')
                # Flash red for error
                for _ in range(2):
                    state.rgb.fill_color(Config.LED_RED)
                    time.sleep(0.5)
                    state.rgb.fill_color(Config.LED_OFF)
                    time.sleep(0.5)
    except Exception as e:
        print(f'Fatal error: {e}')
        # Flash red rapidly and reset
        for _ in range(5):
            state.rgb.fill_color(Config.LED_RED)
            time.sleep(0.2)
            state.rgb.fill_color(Config.LED_OFF)
            time.sleep(0.2)
        machine.reset()

if __name__ == '__main__':
    main()
