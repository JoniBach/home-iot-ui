// Type definitions for Web Bluetooth API
// Project: https://webbluetoothcg.github.io/web-bluetooth/

interface Navigator {
  bluetooth: Bluetooth;
}

interface Bluetooth {
  requestDevice(options: BluetoothRequestDeviceOptions): Promise<BluetoothDevice>;
  getAvailability(): Promise<boolean>;
  onavailabilitychanged: (event: Event) => void;
  addEventListener(type: 'advertisementreceived', listener: (event: Event) => void): void;
  removeEventListener(type: 'advertisementreceived', listener: (event: Event) => void): void;
}

interface BluetoothRequestDeviceOptions {
  acceptAllDevices?: boolean;
  optionalServices?: BluetoothServiceUUID[];
  filters?: BluetoothLEScanFilter[];
}

interface BluetoothLEScanFilter {
  name?: string;
  namePrefix?: string;
  services?: BluetoothServiceUUID[];
  manufacturerData?: BluetoothManufacturerDataFilter[];
  serviceData?: BluetoothServiceDataFilter[];
}

type BluetoothServiceUUID = number | string;
type BluetoothCharacteristicUUID = number | string;
type BluetoothDescriptorUUID = number | string;

interface BluetoothManufacturerDataFilter {
  companyIdentifier: number;
  dataPrefix?: BufferSource;
  mask?: BufferSource;
}

interface BluetoothServiceDataFilter {
  service: BluetoothServiceUUID;
  dataPrefix?: BufferSource;
  mask?: BufferSource;
}

interface BluetoothDevice extends EventTarget {
  readonly id: string;
  readonly name?: string;
  readonly gatt?: BluetoothRemoteGATTServer;
  readonly uuids?: string[];
  readonly serviceData?: Map<string, DataView>;
  readonly manufacturerData?: Map<number, DataView>;
  watchAdvertisements(options?: WatchAdvertisementsOptions): Promise<void>;
  unwatchAdvertisements(): void;
  readonly watchingAdvertisements: boolean;
  addEventListener(type: 'advertisementreceived', listener: (event: Event) => void): void;
  removeEventListener(type: 'advertisementreceived', listener: (event: Event) => void): void;
}

interface WatchAdvertisementsOptions {
  signal?: AbortSignal;
}

interface BluetoothRemoteGATTServer {
  readonly device: BluetoothDevice;
  readonly connected: boolean;
  connect(): Promise<BluetoothRemoteGATTServer>;
  disconnect(): void;
  getPrimaryService(service: BluetoothServiceUUID): Promise<BluetoothRemoteGATTService>;
  getPrimaryServices(service?: BluetoothServiceUUID): Promise<BluetoothRemoteGATTService[]>;
}

interface BluetoothRemoteGATTService extends EventTarget {
  readonly device: BluetoothDevice;
  readonly isPrimary: boolean;
  readonly uuid: string;
  readonly instanceId: string;
  getCharacteristic(characteristic: BluetoothCharacteristicUUID): Promise<BluetoothRemoteGATTCharacteristic>;
  getCharacteristics(characteristic?: BluetoothCharacteristicUUID): Promise<BluetoothRemoteGATTCharacteristic[]>;
  getIncludedService(service: BluetoothServiceUUID): Promise<BluetoothRemoteGATTService>;
  getIncludedServices(service?: BluetoothServiceUUID): Promise<BluetoothRemoteGATTService[]>;
}

interface BluetoothRemoteGATTCharacteristic extends EventTarget {
  readonly service: BluetoothRemoteGATTService;
  readonly uuid: string;
  readonly properties: BluetoothCharacteristicProperties;
  readonly value?: DataView;
  getDescriptor(descriptor: BluetoothDescriptorUUID): Promise<BluetoothRemoteGATTDescriptor>;
  getDescriptors(descriptor?: BluetoothDescriptorUUID): Promise<BluetoothRemoteGATTDescriptor[]>;
  readValue(): Promise<DataView>;
  writeValue(value: BufferSource): Promise<void>;
  writeValueWithResponse(value: BufferSource): Promise<void>;
  writeValueWithoutResponse(value: BufferSource): Promise<void>;
  startNotifications(): Promise<BluetoothRemoteGATTCharacteristic>;
  stopNotifications(): Promise<BluetoothRemoteGATTCharacteristic>;
  addEventListener(type: 'characteristicvaluechanged', listener: (event: Event) => void): void;
  removeEventListener(type: 'characteristicvaluechanged', listener: (event: Event) => void): void;
}

interface BluetoothCharacteristicProperties {
  readonly authenticatedSignedWrites: boolean;
  readonly broadcast: boolean;
  readonly indicate: boolean;
  readonly notify: boolean;
  readonly read: boolean;
  readonly reliableWrite: boolean;
  readonly writableAuxiliaries: boolean;
  readonly write: boolean;
  readonly writeWithoutResponse: boolean;
}

interface BluetoothRemoteGATTDescriptor {
  readonly characteristic: BluetoothRemoteGATTCharacteristic;
  readonly uuid: string;
  readonly value?: DataView;
  readValue(): Promise<DataView>;
  writeValue(value: BufferSource): Promise<void>;
}

declare const BluetoothUUID: {
  getService(name: string): string;
  getService(alias: number): string;
  getCharacteristic(name: string): string;
  getCharacteristic(alias: number): string;
  getDescriptor(name: string): string;
  getDescriptor(alias: number): string;
  canonicalUUID(alias: number): string;
};
