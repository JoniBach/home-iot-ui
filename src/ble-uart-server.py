import M5
import bluetooth
import time
import struct
from micropython import const
import network
from machine import Timer

M5.begin()

# BLE event constants
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)  # New: Write event

# Use integers for UUIDs
_SERVICE_UUID = 0x181A  # Environmental Sensing (example)
_CHAR_UUID = 0x2A6E     # Temperature characteristic (example)

_FLAG_READ = const(0x0002)
_FLAG_WRITE = const(0x0008)  # Add write permission

class NanoC6BLE:
    def __init__(self):
        self.disconnect_timer = Timer(0)
        self.mac_bytes = None
        self.ble = bluetooth.BLE()
        self._char_handle = None
        self.connections = set()
        self.wlan = network.WLAN(network.STA_IF)
        self._resetting = False
        self.init_ble()

    def init_ble(self):
        if not self.wlan.active():
            self.wlan.active(True)
        self.mac_bytes = self.wlan.config('mac')
        print("MAC bytes:", self.mac_bytes)

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.ble_irq)

        # Register GATT service with READ + WRITE characteristic
        self._handles = self.ble.gatts_register_services((
            (bluetooth.UUID(_SERVICE_UUID), ((bluetooth.UUID(_CHAR_UUID), _FLAG_READ | _FLAG_WRITE),)),
        ))
        print("Registered handles:", self._handles)

        if self._handles and len(self._handles) > 0 and len(self._handles[0]) > 0:
            self._char_handle = self._handles[0][0]
            print("Characteristic handle assigned:", self._char_handle)
            # Initialize characteristic with MAC bytes
            self.ble.gatts_write(self._char_handle, self.mac_bytes)
        else:
            raise RuntimeError("Failed to register BLE service or characteristic")

        self.connections = set()

        self.advertise(name="NanoC6-" + ''.join('{:02X}'.format(b) for b in self.mac_bytes))

    def ble_irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print("Connected, conn_handle:", conn_handle)
            self.connections.add(conn_handle)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print("Disconnected, conn_handle:", conn_handle)
            self.connections.discard(conn_handle)
            
            # Only restart if we're not already in the process of resetting
            if not hasattr(self, '_resetting'):
                self._reset_ble_service()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self._char_handle:
                # Read what was written
                value = self.ble.gatts_read(self._char_handle)
                print("Received write:", value)
                
                try:
                    # If we received "OK", disconnect and reset
                    if value == b"OK":
                        print("Client confirmed data received, initiating clean disconnect...")
                        # Set resetting flag to prevent multiple reset attempts
                        self._resetting = True
                        # Send final ACK before disconnecting
                        self.ble.gatts_write(self._char_handle, b"ACK")
                        # Let the client know we're done
                        time.sleep_ms(100)
                        self.disconnect(conn_handle)
                    else:
                        # For other messages, just send acknowledgment
                        self.ble.gatts_write(self._char_handle, b"ACK")
                        print("Sent ACK to client")
                        
                except Exception as e:
                    print("Error handling client message:", e)
    
    def _reset_ble_service(self):
        print("Resetting BLE service...")
        try:
            # Set reset flag first
            self._resetting = True
            
            # Stop advertising first
            try:
                self.ble.gap_advertise(None)
                time.sleep_ms(100)
            except Exception as e:
                print("Error stopping advertising:", e)
            
            # Disconnect all connections
            for conn_handle in list(self.connections):
                try:
                    self.ble.gap_disconnect(conn_handle)
                except Exception as e:
                    print(f"Error disconnecting handle {conn_handle}:", e)
            
            # Clear connections
            self.connections.clear()
            
            # Stop BLE
            try:
                self.ble.active(False)
                time.sleep_ms(500)
            except Exception as e:
                print("Error deactivating BLE:", e)
            
            # Create a new BLE instance
            self.ble = bluetooth.BLE()
            self.ble.active(True)
            time.sleep_ms(100)
            
            # Set up IRQ handler
            self.ble.irq(self.ble_irq)
            
            # Re-register services
            self._handles = self.ble.gatts_register_services([
                (bluetooth.UUID(_SERVICE_UUID), [
                    (bluetooth.UUID(_CHAR_UUID), _FLAG_READ | _FLAG_WRITE)
                ])
            ])
            
            if not self._handles or not self._handles[0]:
                raise RuntimeError("Failed to register BLE service")
                
            self._char_handle = self._handles[0][0]
            self.ble.gatts_write(self._char_handle, self.mac_bytes)
            
            # Restart advertising with a new name
            name = f"NanoC6-{''.join('{:02X}'.format(b) for b in self.mac_bytes)}"
            self.advertise(name=name)
            
            print("BLE service reset complete, advertising as:", name)
            
        except Exception as e:
            print("Error during BLE reset:", e)
            # Try a hard reset if soft reset fails
            try:
                import machine
                print("Performing hard reset...")
                machine.reset()
            except Exception as e2:
                print("Hard reset failed:", e2)
        finally:
            if hasattr(self, '_resetting'):
                del self._resetting

    def disconnect(self, conn_handle):
        try:
            self.ble.gap_disconnect(conn_handle)
        except Exception as e:
            print("Error during disconnect:", e)

    def stop_ble(self):
        print("Stopping BLE advertising and shutting down BLE")
        try:
            self.ble.gap_advertise(None)
            self.ble.active(False)
        except Exception as e:
            print("Error during BLE shutdown:", e)

    def advertise(self, interval_us=100_000, name="NanoC6-Info", services=None):
        payload = self.advertising_payload(name=name, services=services or [_SERVICE_UUID])
        self.ble.gap_advertise(interval_us, bytes(payload))
        print("Advertising as:", name)

    def advertising_payload(self, limited_disc=False, br_edr=False, name=None, services=None):
        payload = bytearray()

        def _append(adv_type, value):
            payload.append(len(value) + 1)
            payload.append(adv_type)
            payload.extend(value)

        flags = (0x02 if limited_disc else 0x06) + (0x00 if br_edr else 0x04)
        _append(0x01, struct.pack("B", flags))  # Flags

        if name:
            _append(0x09, name.encode())  # Complete Local Name

        if services:
            for uuid_int in services:
                b = struct.pack("<H", uuid_int)
                _append(0x03, b)  # Complete List of 16-bit Service Class UUIDs

        return payload

    def run(self):
        while True:
            time.sleep(1)

if __name__ == "__main__":
    try:
        ble_app = NanoC6BLE()
        ble_app.run()
    except Exception as e:
        print("Fatal error:", e)
