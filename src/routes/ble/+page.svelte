<script lang="ts">
	let devices: any[] = [];
	let isScanning = false;
	let error = null;

	const updateStatus = (id: string, status: string) => {
		const i = devices.findIndex((d) => d.device.id === id);
		if (i > -1) ((devices[i].status = status), (devices = [...devices]));
	};

	const scanDevices = async () => {
		try {
			if (!navigator.bluetooth) throw new Error('Web Bluetooth not supported');
			isScanning = true;
			error = null;
			const device = await navigator.bluetooth.requestDevice({
				filters: [{ namePrefix: 'NanoC6' }],
				optionalServices: ['6e400001-b5a3-f393-e0a9-e50e24dcca9e']
			});
			if (!devices.some((d) => d.device.id === device.id)) {
				devices = [...devices, { device, connected: false, status: 'Found' }];
				connectDevice(device.id);
			}
		} catch (err: any) {
			if (err.name !== 'NotFoundError') error = `Scan failed: ${err.message}`;
		} finally {
			isScanning = false;
		}
	};

	const connectDevice = async (id: string) => {
		const i = devices.findIndex((d) => d.device.id === id);
		if (i === -1) return;
		updateStatus(id, 'Connecting...');
		try {
			const server = await devices[i].device.gatt?.connect();
			if (!server) throw new Error('GATT failed');
			for (const service of await server.getPrimaryServices()) {
				const chars = await service.getCharacteristics();
				const char = chars.find(
					(c) => c.properties.write || c.properties.writeWithoutResponse || c.properties.notify
				);
				if (char) {
					devices[i].characteristic = char;
					devices[i].connected = true;
					devices = [...devices];
					if (char.properties.notify) setupNotifications(id, char);
					break;
				}
			}
			updateStatus(id, 'Connected');
		} catch (err: any) {
			updateStatus(id, `Error: ${err.message}`);
		}
	};

	const setupNotifications = async (id: string, char: BluetoothRemoteGATTCharacteristic) => {
		try {
			await char.startNotifications();
			char.addEventListener('characteristicvaluechanged', (e: any) => {
				if (e.target.value) {
					const i = devices.findIndex((d) => d.device.id === id);
					if (i > -1) {
						devices[i].rawData = new Uint8Array(e.target.value.buffer);
						devices[i].lastUpdate = new Date().toLocaleTimeString();
						devices = [...devices];
					}
				}
			});
			updateStatus(id, 'Receiving data');
		} catch (err: any) {
			updateStatus(id, `Notification error: ${err.message}`);
		}
	};

	const registerDevice = async (id: string) => {
		const i = devices.findIndex((d) => d.device.id === id);
		if (i === -1 || !devices[i].characteristic) return;
		updateStatus(id, 'Registering...');
		try {
			const char = devices[i].characteristic;
			await char.writeValue(new TextEncoder().encode('REGISTER'));
			await new Promise((resolve) => {
				const timeout = setTimeout(
					() => (updateStatus(id, 'Registration timeout'), resolve(false)),
					10000
				);
				const handler = (e: any) => {
					if (e.target.value) {
						const resp = new TextDecoder().decode(e.target.value);
						if (resp.includes('REGISTERED')) {
							clearTimeout(timeout);
							char.removeEventListener('characteristicvaluechanged', handler);
							updateStatus(id, 'Registration successful');
							setTimeout(() => disconnectDevice(id), 500);
							resolve(true);
						} else if (resp.includes('REGISTER_FAILED')) {
							clearTimeout(timeout);
							char.removeEventListener('characteristicvaluechanged', handler);
							updateStatus(id, 'Registration failed');
							resolve(false);
						}
					}
				};
				char.addEventListener('characteristicvaluechanged', handler);
			});
		} catch (err: any) {
			updateStatus(id, `Registration error: ${err.message}`);
		}
	};

	const disconnectDevice = async (id: string) => {
		const i = devices.findIndex((d) => d.device.id === id);
		if (i === -1) return;
		try {
			if (devices[i].device.gatt?.connected) await devices[i].device.gatt.disconnect();
			devices[i] = {
				...devices[i],
				connected: false,
				status: 'Disconnected',
				characteristic: undefined
			};
			devices = [...devices];
		} catch (err: any) {
			updateStatus(id, `Disconnect error: ${err.message}`);
		}
	};

	const forgetDevice = (id: string) => (devices = devices.filter((d) => d.device.id !== id));
	const formatHex = (data: Uint8Array) =>
		Array.from(data)
			.map((b) => b.toString(16).padStart(2, '0').toUpperCase())
			.join(' ');
	const formatAscii = (data: Uint8Array) =>
		String.fromCharCode(...data)
			.split('')
			.map((c) => (c.charCodeAt(0) < 32 ? '.' : c))
			.join('');
</script>

<div>
	<h1>NanoC6 Device Registration</h1>
	<button on:click={scanDevices} disabled={isScanning}
		>{isScanning ? 'Scanning...' : 'Scan for Devices'}</button
	>
	{#if error}<div>{error}</div>{/if}
	{#if devices.length}
		{#each devices as d (d.device.id)}
			<div>
				<div>
					<h3>{d.device.name || 'NanoC6 Device'}</h3>
					<span>{d.status}</span>
				</div>
				<div>
					{#if d.connected}
						<button
							on:click={() => registerDevice(d.device.id)}
							disabled={d.status?.includes('Registering')}
							>{d.status?.includes('Registering') ? 'Registering...' : 'Register'}</button
						>
						<button on:click={() => disconnectDevice(d.device.id)}>Disconnect</button>
					{:else}
						<button on:click={() => connectDevice(d.device.id)} disabled={isScanning}
							>Connect</button
						>
					{/if}
					<button on:click={() => forgetDevice(d.device.id)}>Forget</button>
				</div>
				{#if d.rawData}
					<div>
						<div><strong>Last Update:</strong> {d.lastUpdate || 'N/A'}</div>
						<div><strong>Raw Data ({d.rawData.length} bytes):</strong></div>
						<pre>{formatHex(d.rawData)}</pre>
						<div><strong>ASCII:</strong></div>
						<pre>{formatAscii(d.rawData)}</pre>
					</div>
				{/if}
			</div>
		{/each}
	{:else if isScanning}<p>Scanning for BLE devices...</p>
	{:else}<p>No devices found. Click "Scan for Devices" to start.</p>
	{/if}
</div>
