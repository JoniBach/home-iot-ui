<script lang="ts">
	import { onMount } from 'svelte';

	// No hardcoded UUIDs - we'll discover services and characteristics dynamically

	interface DeviceInfo {
		device: BluetoothDevice;
		connected: boolean;
		status?: string;
		macAddress?: string;
		rawData?: Uint8Array;
		lastUpdate?: string;
		server?: BluetoothRemoteGATTServer;
		service?: BluetoothRemoteGATTService;
		characteristic?: BluetoothRemoteGATTCharacteristic;
		nofityCharacteristic?: BluetoothRemoteGATTCharacteristic;
		isNotifying?: boolean;
	}

	let devices: DeviceInfo[] = [];

	let isScanning = false;
	let error: string | null = null;

	async function connectToDevice(device: BluetoothDevice) {
		try {
			const deviceIndex = devices.findIndex((d) => d.device.id === device.id);
			if (deviceIndex === -1) return false;

			// Update device status
			updateDeviceStatus(deviceIndex, 'Connecting...');

			// Connect to the GATT Server
			const server = await device.gatt?.connect();
			if (!server) throw new Error('Failed to connect to GATT server');

			// Get all primary services
			const services = await server.getPrimaryServices();
			console.log('Found services:', services);

			// Find the first service with characteristics we can work with
			for (const service of services) {
				try {
					const characteristics = await service.getCharacteristics();
					console.log(`Service ${service.uuid} characteristics:`, characteristics);

					// Find characteristics with notify or write properties
					const notifyChar = characteristics.find(c => c.properties.notify);
					const writeChar = characteristics.find(c => c.properties.write || c.properties.writeWithoutResponse);

					if (notifyChar || writeChar) {
						// Update device info with connection details
						const currentDeviceIndex = devices.findIndex((d) => d.device === device);
						if (currentDeviceIndex !== -1) {
							devices[currentDeviceIndex] = {
								...devices[currentDeviceIndex],
								server,
								service,
								characteristic: writeChar,
								nofityCharacteristic: notifyChar,
								connected: true
							};
							devices = [...devices];

							// Set up notifications if available
							if (notifyChar) {
								await setupDeviceNotifications(device, notifyChar, currentDeviceIndex);
							}
							break;
						}
					}
				} catch (err) {
					console.warn(`Error processing service ${service.uuid}:`, err);
				}
			}

			// Update device status
			updateDeviceStatus(deviceIndex, 'Connected');
			return true;
		} catch (err) {
			const error = err as Error;
			console.error('Connection error:', error);
			updateDeviceStatus(
				devices.findIndex((d) => d.device.id === device.id),
				`Error: ${error.message}`
			);
			return false;
		}
	}

	function updateDeviceStatus(deviceIndex: number, status: string) {
		if (deviceIndex !== -1) {
			devices[deviceIndex].status = status;
			devices = [...devices];
		}
	}

	async function setupDeviceNotifications(
		device: BluetoothDevice,
		characteristic: BluetoothRemoteGATTCharacteristic,
		deviceIndex: number
	) {
		console.log('Setting up notifications for characteristic:', characteristic.uuid);
		
		// Update device to show notifications are being set up
		updateDeviceStatus(deviceIndex, 'Setting up notifications...');

		try {
			// Initial read of the characteristic value
			try {
				console.log('Reading initial characteristic value...');
				const value = await characteristic.readValue();
				const deviceIdx = devices.findIndex((d) => d.device === device);
				if (deviceIdx !== -1) {
					const rawData = new Uint8Array(value.buffer);
					console.log('Initial characteristic value:', Array.from(rawData).map(b => b.toString(16).padStart(2, '0')).join(' '));
					devices[deviceIdx].rawData = rawData;
					devices[deviceIdx].lastUpdate = new Date().toLocaleTimeString();
					devices = [...devices];
				}
			} catch (readError) {
				console.warn('Could not read characteristic value:', readError);
			}

			// Try to start notifications if available
			try {
				console.log('Starting notifications...');
				await characteristic.startNotifications();
				
				// Update device to show notifications are active
				const deviceIdx = devices.findIndex((d) => d.device === device);
				if (deviceIdx !== -1) {
					devices[deviceIdx].isNotifying = true;
					devices = [...devices];
				}

				// Define the notification handler
				const handleNotification = (event: Event) => {
					try {
						const target = event.target as BluetoothRemoteGATTCharacteristic;
						const value = target.value;
						if (!value) {
							console.warn('Received notification with no data');
							return;
						}

						const deviceIdx = devices.findIndex((d) => d.device === device);
						if (deviceIdx !== -1) {
							const rawData = new Uint8Array(value.buffer);
							console.log('Received data:', Array.from(rawData).map(b => b.toString(16).padStart(2, '0')).join(' '));
							
							devices[deviceIdx].rawData = rawData;
							devices[deviceIdx].lastUpdate = new Date().toLocaleTimeString();
							devices = [...devices];
						}
					} catch (notifyError) {
						console.error('Error handling notification:', notifyError);
					}
				};
				characteristic.addEventListener('characteristicvaluechanged', handleNotification);
				console.log('Notification handler added');
				
				// Update status to show notifications are active
				updateDeviceStatus(deviceIndex, 'Connected - Receiving data');
			} catch (notifyError) {
				console.error('Notification setup failed:', notifyError);
				updateDeviceStatus(deviceIndex, 'Connected - Notification error');
			}
		} catch (err) {
			const error = err as Error;
			console.error('Error setting up notifications:', error);
			updateDeviceStatus(deviceIndex, `Error: ${error.message}`);
		}
		
		// Store the cleanup function
		const cleanup = () => {
			console.log('Cleaning up notification handler');
			characteristic.removeEventListener('characteristicvaluechanged', handleNotification);
		};
		
		// Return cleanup function that can be called when needed
		return cleanup;
	}

	async function disconnectDevice(device: BluetoothDevice) {
		try {
			const deviceIndex = devices.findIndex((d) => d.device === device);
			if (deviceIndex === -1) return;

			try {
				// Notify server we're disconnecting
				if (devices[deviceIndex].characteristic) {
					await devices[deviceIndex].characteristic?.writeValue(new TextEncoder().encode('DONE'));
					console.log('Sent DONE signal to server');
					// Wait a moment for the server to process the disconnection
					await new Promise((resolve) => setTimeout(resolve, 500));
				}
			} catch (e) {
				console.warn('Could not send DONE signal to server:', e);
			}

			// Disconnect from the device
			if (devices[deviceIndex].server?.connected) {
				const server = devices[deviceIndex].server;
				if (server) {
					await server.disconnect();
				}
			}

			devices[deviceIndex] = {
				...devices[deviceIndex],
				connected: false,
				status: 'Disconnected',
				server: undefined,
				service: undefined,
				characteristic: undefined
			};
			devices = [...devices];
		} catch (err) {
			console.error('Disconnect failed:', err);
		}
	}

	// Polling function for devices that don't support notifications
	function startPolling(
		device: BluetoothDevice,
		characteristic: BluetoothRemoteGATTCharacteristic
	) {
		const intervalId = setInterval(async () => {
			try {
				if (!device.gatt?.connected) {
					clearInterval(intervalId);
					return;
				}

				const value = await characteristic.readValue();
				const status = new TextDecoder().decode(value);

				const deviceIndex = devices.findIndex((d) => d.device === device);
				if (deviceIndex !== -1) {
					devices[deviceIndex].status = `Polled: ${status}`;
					devices = [...devices];
				}
			} catch (pollError) {
				console.error('Polling error:', pollError);
			}
		}, 2000); // Poll every 2 seconds

		// Clean up interval on disconnect
		// @ts-ignore - gattserverdisconnected is a valid event but not in TypeScript types
		device.addEventListener('gattserverdisconnected', () => {
			clearInterval(intervalId);
		});
	}

	async function requestBluetooth() {
		try {
			if (!navigator.bluetooth) {
				throw new Error('Web Bluetooth API is not supported in this browser');
			}

			isScanning = true;
			error = null;

			// Request any BLE device with any service
			let device;
			try {
				device = await navigator.bluetooth.requestDevice({
					filters: [{ namePrefix: 'NanoC6' }],
					optionalServices: [] // Will be populated with discovered services
				});
			} catch (err) {
				console.log('Could not find device with name prefix, trying service filter only...');
				// If that fails, accept any BLE device
				device = await navigator.bluetooth.requestDevice({
					acceptAllDevices: true,
					optionalServices: []
				});
			}

			// Add the device to the list if not already present
			if (!devices.some((d) => d.device.id === device.id)) {
				const newDevice: DeviceInfo = {
					device,
					connected: false,
					status: 'Disconnected'
				};
				devices = [...devices, newDevice];

				// Connect to the device
				await connectToDevice(device);
			}
		} catch (err: unknown) {
			const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
			if ((err as { name?: string }).name !== 'NotFoundError') {
				error = `Failed to scan for Bluetooth devices: ${errorMessage}`;
				console.error('Bluetooth error:', err);
			}
		} finally {
			isScanning = false;
		}
	}

	async function unpairDevice(deviceId: string) {
		try {
			// Get the device object from the list
			const deviceIndex = devices.findIndex((d) => d.device.id === deviceId);
			if (deviceIndex === -1) return;

			const device = devices[deviceIndex];

			// Disconnect if connected
			if (device.connected) {
				await disconnectDevice(device.device);
			}

			// Remove the device from the browser's remembered devices
			try {
				if ('forget' in navigator.bluetooth) {
					// @ts-ignore - forget() is not in TypeScript definitions yet
					await navigator.bluetooth.forget(device.device.id);
				}
			} catch (forgetError) {
				console.warn('Could not forget device:', forgetError);
				// Continue even if forget fails
			}

			// Remove from our local list
			devices = devices.filter((d) => d.device.id !== deviceId);
		} catch (err: unknown) {
			const errorMessage = err instanceof Error ? err.message : 'Failed to unpair device';
			error = `Error: ${errorMessage}`;
			console.error('Unpair error:', err);
		}
	}

	async function registerDevice(device: BluetoothDevice) {
		try {
			const deviceIndex = devices.findIndex((d) => d.device.id === device.id);
			if (deviceIndex === -1) {
				throw new Error('Device not found');
			}

			// Make sure we're connected
			if (!devices[deviceIndex].connected || !devices[deviceIndex].characteristic) {
				// Try to connect first
				const connected = await connectToDevice(device);
				if (!connected) {
					throw new Error('Failed to connect to device');
				}
			}

			updateDeviceStatus(deviceIndex, 'Registering...');

			// Send REGISTER command if we have a writable characteristic
			if (devices[deviceIndex].characteristic) {
				const encoder = new TextEncoder();
				await devices[deviceIndex].characteristic?.writeValue(encoder.encode('REGISTER'));
			} else {
				throw new Error('No writable characteristic found for registration');
			}

			// Store the cleanup function
			// Store cleanup function for notification handler
			let cleanupNotification: (() => void) | null = null;
			
			// Wait for registration confirmation
			return new Promise((resolve) => {
				const timeout = setTimeout(() => {
					if (cleanupNotification) cleanupNotification();
					updateDeviceStatus(deviceIndex, 'Registration timeout');
					resolve(false);
				}, 10000);

				// Use the notify characteristic if available (fixing the typo in the property name)
				const notifyChar = devices[deviceIndex].nofityCharacteristic;
				if (notifyChar) {
					// Store the notification handler for cleanup
					const notificationHandler = (event: Event) => {
						const target = event.target as BluetoothRemoteGATTCharacteristic;
						const value = target.value;
						if (value) {
							const response = new TextDecoder().decode(value);
							console.log('Registration response:', response);

							if (response.includes('REGISTERED')) {
								clearTimeout(timeout);
								if (cleanupNotification) cleanupNotification();
								updateDeviceStatus(deviceIndex, 'Registration successful');
								// Small delay to ensure the message is sent before disconnecting
								setTimeout(() => {
									// Disconnect gracefully
									disconnectDevice(device).then(() => {
										resolve(true);
									});
								}, 500);
							}
						}
					};

					notifyChar.startNotifications()
						.then(() => {
							notifyChar.addEventListener('characteristicvaluechanged', notificationHandler);
						})
						.catch((err: Error) => {
							console.error('Failed to start notifications:', err);
							updateDeviceStatus(deviceIndex, 'Notification error');
						});

					// Store cleanup function
					cleanupNotification = () => {
						try {
							notifyChar.stopNotifications().catch((err: Error) => 
								console.warn('Error stopping notifications:', err)
							);
							notifyChar.removeEventListener('characteristicvaluechanged', notificationHandler);
						} catch (e) {
							console.warn('Error cleaning up notifications:', e);
						}
					};
				} else {
					console.warn('No notification characteristic available for this device');
				}
			});
		} catch (err) {
			const error = err as Error;
			console.error('Registration error:', error);
			const deviceIndex = devices.findIndex((d) => d.device.id === device.id);
			if (deviceIndex !== -1) {
				updateDeviceStatus(deviceIndex, `Error: ${error.message}`);
			}
			return false;
		}
	}

	function clearDevices() {
		devices = [];
		error = null;
	}
</script>

<div>
	<h1>NanoC6 Device Registration</h1>

	<button on:click={requestBluetooth} disabled={isScanning}>
		{isScanning ? 'Scanning...' : 'Scan for Devices'}
	</button>

	{#if error}
		<div>{error}</div>
	{/if}

	{#if devices.length > 0}
		<div>
			{#each devices as device, index (index)}
				<div>
					<div>
						<h3>{device.device.name || 'NanoC6 Device'}</h3>
						<div>Status: {device.status || 'Disconnected'}</div>
					</div>

					<div>
						{#if device.connected}
							<button
								on:click|stopPropagation={() => registerDevice(device.device)}
								disabled={device.status?.includes('Registering')}
							>
								{device.status?.includes('Registering') ? 'Registering...' : 'Register Device'}
							</button>
							<button on:click|stopPropagation={() => disconnectDevice(device.device)}>
								Disconnect
							</button>
						{:else}
							<button
								on:click|stopPropagation={() => connectToDevice(device.device)}
								disabled={isScanning}
							>
								Connect
							</button>
						{/if}
						<button on:click|stopPropagation={() => unpairDevice(device.device.id)}>
							Forget
						</button>
					</div>

					{#if device.rawData}
						<div>
							<div><strong>MAC:</strong> {device.macAddress || 'N/A'}</div>
							<div><strong>Last Update:</strong> {device.lastUpdate || 'N/A'}</div>
							<div><strong>Status:</strong> {device.status || 'Unknown'}</div>
							<div><strong>Notifications:</strong> {device.isNotifying ? 'Active' : 'Inactive'}</div>
							<div>
								<strong>Raw Data ({device.rawData?.length || 0} bytes):</strong>
								<pre>{device.rawData ? 
									Array.from(device.rawData)
										.map((byte) => byte.toString(16).padStart(2, '0').toUpperCase())
										.join(' ')
									: 'No data received'}</pre>
							</div>
							<div>
								<strong>ASCII:</strong>
								<pre>{device.rawData ? 
									String.fromCharCode(...device.rawData)
										.split('')
										.map(c => c.charCodeAt(0) < 32 ? '.' : c)
										.join('')
									: 'N/A'}</pre>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{:else if isScanning}
		<p>Scanning for BLE devices...</p>
	{:else}
		<p>No devices found. Click "Scan for Devices" to start scanning.</p>
	{/if}
</div>

<style>
	/* All styles removed */
</style>
