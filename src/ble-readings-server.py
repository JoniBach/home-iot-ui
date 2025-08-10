import os, sys, io
import M5
from M5 import *
from hardware import RGB
import requests2
import network
import time
import ubluetooth
from unit import ENVUnit
from hardware import I2C
from hardware import Pin
import ubinascii
import machine

# BLE Configuration
_SERVICE_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')  # Nordic UART Service
_CHAR_UUID = ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E')    # RX Characteristic
_FLAG_READ = 0x0002
_FLAG_WRITE = 0x0008
_FLAG_NOTIFY = 0x0010

# Global variables
http_req = None
wlan = None
rgb = None
i2c0 = None
env4_0 = None
ble = None

# Device state
mac_address = None
isPairing = False
isConnecting = False
readings = None
deviceExists = False
isRegistered = False

class BLEReadingsServer:
    def __init__(self):
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.connections = set()
        self._char_handle = None
        self._reset_ble()
        
    def _reset_ble(self):
        try:
            self.ble.active(False)
            time.sleep_ms(500)
            self.ble.active(True)
            self._init_ble()
        except Exception as e:
            print("Error resetting BLE:", e)
            machine.reset()
    
    def _init_ble(self):
        # Set up the BLE service and characteristic
        self.ble.irq(self._ble_irq)
        
        # Create the service and characteristic
        service = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
        self.characteristic = (ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'), 
                             _FLAG_READ | _FLAG_WRITE | _FLAG_NOTIFY)
        
        # Register the service
        services = (
            (service, (self.characteristic,)),
        )
        
        try:
            # Register services
            ((self._char_handle,),) = self.ble.gatts_register_services(services)
            print('BLE services registered')
        except Exception as e:
            print('Failed to register BLE services:', e)
            machine.reset()
        
        # Set initial value
        self.ble.gatts_write(self._char_handle, 'Ready')
        
        # Start advertising
        self._advertise()
    
    def _advertise(self, interval_us=500000):
        # Get MAC address for advertising name
        mac = ubinascii.hexlify(self.ble.config('mac')[1], ':').decode().upper()
        name = 'NanoC6-{}'.format(mac.replace(':', '')[-6:])
        
        # Build advertising data
        adv_data = bytearray([
            0x02, 0x01, 0x06,  # Flags
            0x02, 0x0A, 0x1A,  # 16-bit Service UUID
            len(name) + 1, 0x09  # Complete local name
        ])
        adv_data.extend(name.encode('utf-8'))
        
        # Start advertising
        try:
            self.ble.gap_advertise(
                interval_us,
                adv_data=bytes(adv_data),
                connectable=True
            )
            print('Advertising as {}...'.format(name))
        except Exception as e:
            print('Failed to start advertising:', e)
            machine.reset()
    
    def _ble_irq(self, event, data):
        if event == 1:  # _IRQ_CENTRAL_CONNECT
            # A central has connected
            conn_handle, _, _ = data
            self.connections.add(conn_handle)
            print('Connected:', conn_handle)
            
        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            # A central has disconnected
            conn_handle, _, _ = data
            if conn_handle in self.connections:
                self.connections.remove(conn_handle)
            print('Disconnected:', conn_handle)
            # Restart advertising
            self._advertise()
            
        elif event == 3:  # _IRQ_GATTS_WRITE
            # A central has written to our characteristic
            conn_handle, value_handle = data
            if value_handle == self._char_handle:
                value = self.ble.gatts_read(value_handle)
                print('Received:', value)
                
                try:
                    if value == b'GET_READINGS':
                        self._send_readings()
                    elif value == b'REGISTER':
                        self._handle_registration(conn_handle)
                    else:
                        # Echo back the received data
                        self.ble.gatts_write(self._char_handle, value)
                except Exception as e:
                    print('Error handling BLE write:', e)
    
    def _send_readings(self):
        if not self.connections:
            return
            
        # Take sensor readings
        temp = env4_0.read_temperature()
        humidity = env4_0.read_humidity()
        pressure = env4_0.read_pressure()
        
        # Format readings as JSON
        readings = {
            'temperature': temp,
            'humidity': humidity,
            'pressure': pressure,
            'timestamp': time.time()
        }
        
        # Send readings to all connected devices
        for conn_handle in self.connections:
            try:
                self.ble.gatts_write(self._char_handle, str(readings).encode())
            except Exception as e:
                print("Error sending readings:", e)
    
    def _handle_registration(self, conn_handle):
        # In a real implementation, you would add the device to your registered devices list
        # and potentially store it in non-volatile memory
        try:
            # Send registration confirmation
            self.ble.gatts_write(self._char_handle, b'REGISTERED')
            print("Device registered")
        except Exception as e:
            print("Registration error:", e)

def check_device_registered():
    global isRegistered, deviceExists, mac_address, last_registration_check
    print('Checking if device is registered...')
    try:
        response = requests2.get(
            f'https://odabslohlhkklziizpeh.supabase.co/rest/v1/devices?mac_address=eq.{mac_address}&select=id',
            headers={
                'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'
            }
        )
        
        was_registered = isRegistered  # Store previous state
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                isRegistered = True
                deviceExists = True
                print('Device is registered')
                # Only update LED if state changed
                if not was_registered:
                    rgb.fill_color(0x000000)  # Turn off LED when newly registered
            else:
                isRegistered = False
                print('Device is not registered')
                if was_registered:  # If we were registered but now we're not
                    rgb.fill_color(0xffffff)  # Turn white when unregistered
        else:
            print(f'Error checking registration status: {response.status_code}')
            isRegistered = was_registered  # Keep previous state on error
            
    except Exception as e:
        print('Error checking device registration:', e)
        isRegistered = False
    finally:
        if 'response' in locals():
            response.close()
            
    last_registration_check = time.ticks_ms()

def register_device():
    global http_req, mac_address, isRegistered, deviceExists, last_registration_check, force_immediate_reading
    try:
        print('Registering device...')
        http_req = requests2.post(
            'https://odabslohlhkklziizpeh.supabase.co/rest/v1/devices',
            json={
                'mac_address': mac_address,
                'name': f'NanoC6-{mac_address[-6:]}',
                'connected_at': time.time()
            },
            headers={
                'Content-Type': 'application/json',
                'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ',
                'Prefer': 'return=representation'
            }
        )
        
        if http_req.status_code == 201:
            print('Device registered successfully')
            isRegistered = True
            deviceExists = True
            rgb.fill_color(0x000000)  # Turn off LED on successful registration
            last_registration_check = time.ticks_ms()
            
            # Set flag to take immediate reading in the next cycle
            print("Scheduling immediate reading after registration...")
            force_immediate_reading = True
            return True
        else:
            print('Failed to register device:', http_req.status_code, http_req.text)
            return False
            
    except Exception as e:
        print('Error registering device:', e)
        return False
    finally:
        if http_req:
            http_req.close()

def handleWlan():
    global wlan, mac_address
    mac_bytes = wlan.config('mac')
    mac_address = ''.join('{:02X}'.format(b) for b in mac_bytes)
    print(f'MAC Address: {mac_address}')

def takeReadings():
    global env4_0, http_req, mac_address
    print('Taking readings...')
    
    try:
        # Take sensor readings
        temp = env4_0.read_temperature()
        humidity = env4_0.read_humidity()
        pressure = env4_0.read_pressure()
        
        print(f'Temperature: {temp}°C, Humidity: {humidity}%, Pressure: {pressure}hPa')
        
        # Send to cloud
        http_req = requests2.post(
            'https://odabslohlhkklziizpeh.supabase.co/rest/v1/readings',
            data=requests2.urlencode({
                'mac_address': mac_address,
                'temperature': temp,
                'humidity': humidity,
                'pressure': pressure,
                'sensor': 'm5_env_4'
            }),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'
            }
        )
        
        if str(http_req.status_code)[0] == '2':
            print('Readings sent to cloud!')
            return True
        else:
            print('Failed to send readings to cloud')
            print(f'Status: {http_req.status_code}, Reason: {http_req.reason}')
            return False
            
    except Exception as e:
        print('Error in takeReadings:', e)
        return False
    finally:
        if http_req:
            http_req.close()

# Track the last reading time to prevent rapid cycling
last_reading_time = 0
last_registration_check = 0
READING_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes in milliseconds
force_immediate_reading = False

def cycle():
    global rgb, last_reading_time, force_immediate_reading
    current_time = time.ticks_ms()
    
    # Check if we should force an immediate reading (after registration/startup)
    if not force_immediate_reading:
        # Only take a reading if enough time has passed
        if time.ticks_diff(current_time, last_reading_time) < READING_INTERVAL_MS:
            return
    
    print('Starting reading cycle...')
    last_reading_time = current_time
    force_immediate_reading = False  # Reset the flag after using it
    
    # Take the reading without any LED feedback
    success = takeReadings()
    print('Reading cycle complete')

def start_pairing_mode():
    global ble, rgb, isPairing
    print('Starting BLE pairing mode...')
    rgb.fill_color(0x0000ff)  # Blue for pairing mode
    isPairing = True
    
    # Initialize BLE server
    ble = ubluetooth.BLE()
    ble.active(True)
    
    # Set up BLE service and characteristic
    service = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
    characteristic = (ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'), 
                     _FLAG_READ | _FLAG_WRITE)
    
    # Register service
    services = ((service, (characteristic,)),)
    ((char_handle,),) = ble.gatts_register_services(services)
    
    # Set initial value
    ble.gatts_write(char_handle, 'PAIRING')
    
    # Set up advertising
    name = f'NanoC6-{mac_address[-6:]}'
    ble.gap_advertise(
        500000,  # 500ms interval
        adv_data=bytes([
            0x02, 0x01, 0x06,  # Flags
            0x02, 0x0A, 0x1A,  # 16-bit Service UUID
            len(name) + 1, 0x09  # Complete local name
        ]) + name.encode('utf-8'),
        connectable=True
    )
    
    print(f'BLE pairing mode started. Device name: {name}')
    
    # Keep BLE active for 2 minutes or until registered
    start_time = time.ticks_ms()
    registration_successful = False
    
    while isPairing and (time.ticks_diff(time.ticks_ms(), start_time) < 120000):
        # Check for registration command
        value = ble.gatts_read(char_handle)
        if value == b'REGISTER':
            if register_device():
                ble.gatts_write(char_handle, 'REGISTERED')
                isRegistered = True
                registration_successful = True
                print('Registration successful, updating state...')
                break
            else:
                ble.gatts_write(char_handle, 'REGISTER_FAILED')
        time.sleep_ms(100)
    
    # Clean up BLE
    ble.active(False)
    isPairing = False
    print('Exited BLE pairing mode')
    
    # If registration was successful, update the LED and start readings
    if registration_successful:
        print('Starting normal operation after registration')
        # Ensure LED is off after the cycle
        rgb.fill_color(0x000000)
        # Take an immediate reading without showing any LED
        cycle()
        

def btnA_wasHold_event(state):
    global isPairing
    if not isPairing and not isRegistered:
        print('Entering pairing mode...')
        start_pairing_mode()
    else:
        print('Already in pairing mode or device is registered')

def setup():
    global wlan, rgb, i2c0, env4_0, mac_address, isRegistered, last_registration_check, force_immediate_reading
    
    M5.begin()
    BtnA.setCallback(type=BtnA.CB_TYPE.WAS_HOLD, cb=btnA_wasHold_event)
    
    # Initialize hardware
    wlan = network.WLAN(network.STA_IF)
    rgb = RGB()
    rgb.set_brightness(10)
    
    # Initialize I2C and environmental sensor
    try:
        i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
        env4_0 = ENVUnit(i2c=i2c0, type=4)
    except Exception as e:
        print('Failed to initialize I2C or ENV sensor:', e)
        # Continue without sensor for debugging
        pass
    
    # Get MAC address
    handleWlan()
    
    # Initial LED state - start with LED off
    rgb.fill_color(0x000000)
    
    # Check if device is registered
    check_device_registered()
    last_registration_check = time.ticks_ms()
    
    # If registered, schedule an immediate reading
    if isRegistered:
        print("Device is registered, scheduling initial reading...")
        force_immediate_reading = True

def loop():
    global isPairing, isRegistered, rgb
    
    M5.update()
    
    if isPairing:
        # In pairing mode, show solid blue
        rgb.fill_color(0x0000ff)
        time.sleep_ms(100)
        return
        
    # If not registered, show solid white and check status occasionally
    if not isRegistered:
        if time.ticks_diff(time.ticks_ms(), last_registration_check) > 10000:  # Every 10 seconds
            check_device_registered()
        rgb.fill_color(0xffffff)  # White when unregistered
        time.sleep_ms(100)
        return
    
    # If we get here, we're registered
    # Set LED to off during normal operation
    rgb.fill_color(0x000000)
    
    # Only take readings at the specified interval
    cycle()
    
    # Small delay to prevent tight loop
    time.sleep_ms(100)
    
    # Check registration status periodically (less frequently when registered)
    if time.ticks_diff(time.ticks_ms(), last_registration_check) > 300000:  # Every 5 minutes when registered
        check_device_registered()

if __name__ == '__main__':
    try:
        setup()
        while True:
            try:
                loop()
            except Exception as e:
                print('Error in main loop:', e)
                rgb.fill_color(0xff0000)  # Red for error
                time.sleep(1)
                rgb.fill_color(0x000000)
                time.sleep(1)
    except Exception as e:
        print('Fatal error:', e)
        # Blink red LED rapidly to indicate fatal error
        for _ in range(5):
            rgb.fill_color(0xff0000)
            time.sleep(0.2)
            rgb.fill_color(0x000000)
            time.sleep(0.2)
        # Reset on error
        machine.reset()
