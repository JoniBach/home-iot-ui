import os, sys, io
import M5
from M5 import *
from hardware import RGB
import requests2
import network
import time
from unit import ENVUnit
from hardware import I2C
from hardware import Pin



http_req = None
wlan = None
rgb = None
i2c0 = None
env4_0 = None


mac_address = None
isPairing = None
isConnecting = None
readings = None
deviceExists = None

# Describe this function...
def handleConnect():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  print('connecting...')
  http_req = requests2.patch((str('https://odabslohlhkklziizpeh.supabase.co/rest/v1/devices?mac_address=eq.') + str(mac_address)), json={'connected_at':(time.mktime(time.gmtime()))}, headers={'Content-Type': 'application/json','apikey':'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'})
  if (str((http_req.status_code)))[0] == '2':
    rgb.fill_color(0x3366ff)
    print('Connected!')
  else:
    rgb.fill_color(0xff0000)
    print('Failed to connect!')
    print((str((http_req.status_code)) + str((http_req.reason))))
  http_req.close()

# Describe this function...
def handleWlan():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  mac_address = (str('') + str((wlan.config('mac'))))
  print((str('Mac Addresss: ') + str(mac_address)))

# Describe this function...
def handleReadings():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  print('taking readings...')
  readings = {'mac_address':mac_address,'temperature':(env4_0.read_temperature()),'humidity':(env4_0.read_humidity()),'pressure':(env4_0.read_pressure()),'sensor':'m5_env_4'}
  print('sending to server...')
  http_req = requests2.post('https://odabslohlhkklziizpeh.supabase.co/rest/v1/readings', data=requests2.urlencode(readings), headers={'Content-Type': 'application/x-www-form-urlencoded','apikey':'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'})
  if (str((http_req.status_code)))[0] == '2':
    rgb.fill_color(0x33cc00)
    print('Readings sent!')
  else:
    rgb.fill_color(0xff0000)
    print('Readings failed to send!')
    print((str((http_req.status_code)) + str((http_req.reason))))
  http_req.close()

# Describe this function...
def cycle():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  print('Starting Cycle')
  rgb.fill_color(0xffffff)
  time.sleep(2)
  handleReadings()
  time.sleep(2)
  rgb.fill_color(0x000000)
  time.sleep(600)
  print('Cycle Complete')

# Describe this function...
def handleFetchDevice():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  isConnecting = True
  print('fetchingDevice')
  http_req = requests2.get((str('https://odabslohlhkklziizpeh.supabase.co/rest/v1/devices?mac_address=eq.') + str(mac_address)), headers={'Content-Type': 'application/json','apikey':'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9kYWJzbG9obGhra2x6aWl6cGVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ0MTM1NzUsImV4cCI6MjA2OTk4OTU3NX0.yTc4AP0_3XTvyauwcGW8Z_JSufLVpVu6lQ58-vQvhbQ'})
  if (str((http_req.status_code)))[0] == '2':
    rgb.fill_color(0x3366ff)
    print('Connected!')
    print(len(http_req.json()) == 0)
    if len(http_req.json()) == 0:
      deviceExists = False
      rgb.fill_color(0xffffff)
    else:
      deviceExists = True
      rgb.fill_color(0x33ff33)
  else:
    rgb.fill_color(0xff0000)
    print('Failed to connect!')
    print((str((http_req.status_code)) + str((http_req.reason))))
  http_req.close()
  isConnecting = False

# Describe this function...
def handleStartBLEServer():
  global mac_address, isPairing, isConnecting, readings, deviceExists, http_req, wlan, rgb, i2c0, env4_0
  rgb.fill_color(0x3366ff)


def btnA_wasHold_event(state):
  global http_req, wlan, rgb, i2c0, env4_0, mac_address, isPairing, isConnecting, readings, deviceExists
  isPairing = True
  print('pairing...')


def btnA_wasHold_event(state):
  global http_req, wlan, rgb, i2c0, env4_0, mac_address, isPairing, isConnecting, readings, deviceExists
  handleStartBLEServer()


def setup():
  global http_req, wlan, rgb, i2c0, env4_0, mac_address, isPairing, isConnecting, readings, deviceExists

  M5.begin()
  BtnA.setCallback(type=BtnA.CB_TYPE.WAS_HOLD, cb=btnA_wasHold_event)

  wlan = network.WLAN(network.STA_IF)
  rgb = RGB()
  rgb.set_brightness(10)
  rgb.fill_color(0xffffff)
  i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
  env4_0 = ENVUnit(i2c=i2c0, type=4)
  handleWlan()
  handleFetchDevice()


def loop():
  global http_req, wlan, rgb, i2c0, env4_0, mac_address, isPairing, isConnecting, readings, deviceExists
  M5.update()
  if isConnecting == False and deviceExists == True:
    cycle()


if __name__ == '__main__':
  try:
    setup()
    while True:
      loop()
  except (Exception, KeyboardInterrupt) as e:
    try:
      from utility import print_error_msg
      print_error_msg(e)
    except ImportError:
      print("please update to latest firmware")
