<script>
  import { onMount } from 'svelte';
  import * as d3 from 'd3';
  
  export let data;
  
  // Chart containers
  let tempChartContainer;
  let humidityChartContainer;
  let pressureChartContainer;
  
  // Chart dimensions and margins
  const margin = {top: 0, right: 80, bottom: 0, left: 50};
  const width = 800 - margin.left - margin.right;
  const height = 150 - margin.top - margin.bottom;
  
  // Process data for charts
  $: processedData = processData(data.readings);
  
  function processData(readings) {
    // Group data by device (mac_address)
    const dataByDevice = {};
    
    readings.forEach(reading => {
      if (!dataByDevice[reading.mac_address]) {
        dataByDevice[reading.mac_address] = [];
      }
      dataByDevice[reading.mac_address].push({
        date: new Date(reading.created_at),
        temperature: parseFloat(reading.temperature),
        humidity: parseFloat(reading.humidity),
        pressure: parseFloat(reading.pressure)
      });
    });
    
    // Sort each device's readings by date
    Object.keys(dataByDevice).forEach(mac => {
      dataByDevice[mac].sort((a, b) => a.date - b.date);
    });
    
    return dataByDevice;
  }
  
  // Create chart function
  function createChart(container, data, yLabel, valueAccessor, hideXAxis = false, hideLegend = false) {
    if (!container || Object.keys(data).length === 0) return;
    
    // Clear any existing content
    d3.select(container).selectAll('*').remove();
    
    // Adjust margins based on whether X-axis is shown
    const chartMargins = { ...margin };
    if (!hideXAxis) {
      chartMargins.bottom += 20; // Add extra space for X-axis labels
    }
    
    // Create SVG
    const svg = d3.select(container)
      .append('svg')
        .attr('width', width + chartMargins.left + chartMargins.right)
        .attr('height', height + chartMargins.top + chartMargins.bottom)
      .append('g')
        .attr('transform', `translate(${chartMargins.left},${chartMargins.top})`);
    
    // Get all data points for scaling
    const allDataPoints = Object.values(data).flat();
    
    // Set up scales
    const x = d3.scaleTime()
      .domain(d3.extent(allDataPoints, d => d.date))
      .range([0, width]);
      
    const y = d3.scaleLinear()
      .domain([
        d3.min(allDataPoints, d => valueAccessor(d)) * 0.95,
        d3.max(allDataPoints, d => valueAccessor(d)) * 1.05
      ])
      .range([height, 0]);
    
    // Create line generator
    const line = d3.line()
      .x(d => x(d.date))
      .y(d => y(valueAccessor(d)));
    
    // Add X axis
    if (!hideXAxis) {
      svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(x));
    }
    
    // Add Y axis
    svg.append('g')
      .call(d3.axisLeft(y));
    
    // Add Y axis label
    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('y', 0 - margin.left)
      .attr('x', 0 - (height / 2))
      .attr('dy', '1em')
      .style('text-anchor', 'middle')
      .text(yLabel);
    
    // Color scale for different devices
    const color = d3.scaleOrdinal(d3.schemeCategory10)
      .domain(Object.keys(data));
    
    // Function to split data into segments where gaps > 30 minutes
    function splitDataByTimeGap(data, maxGapMinutes = 30) {
      if (data.length === 0) return [];
      
      const segments = [];
      let currentSegment = [data[0]];
      
      for (let i = 1; i < data.length; i++) {
        const prevTime = data[i - 1].date.getTime();
        const currTime = data[i].date.getTime();
        const gapMinutes = (currTime - prevTime) / (1000 * 60);
        
        if (gapMinutes > maxGapMinutes) {
          segments.push(currentSegment);
          currentSegment = [data[i]];
        } else {
          currentSegment.push(data[i]);
        }
      }
      
      if (currentSegment.length > 0) {
        segments.push(currentSegment);
      }
      
      return segments;
    }
    
    // Draw lines for each device
    Object.entries(data).forEach(([mac, deviceData]) => {
      // Split data into segments with gaps > 30 minutes
      const segments = splitDataByTimeGap(deviceData);
      
      // Draw each segment as a separate path
      segments.forEach(segment => {
        svg.append('path')
          .datum(segment)
          .attr('fill', 'none')
          .attr('stroke', color(mac))
          .attr('stroke-width', 1.5)
          .attr('d', line);
      });
    });
    
    if (!hideLegend) {
    // Add legend
    const legend = svg.selectAll('.legend')
      .data(Object.keys(data))
      .enter().append('g')
        .attr('class', 'legend')
        .attr('transform', (d, i) => `translate(0,${i * 20})`);
    
    legend.append('rect')
      .attr('x', width - 18)
      .attr('width', 18)
      .attr('height', 18)
      .style('fill', color);
    
    legend.append('text')
      .attr('x', width - 24)
      .attr('y', 9)
      .attr('dy', '.35em')
      .style('text-anchor', 'end')
      .style('font-family', 'monospace')
      .text(d => d);
    }
  }
  
  // Create charts when component mounts or data changes
  $: if (processedData) {
    createChart(tempChartContainer, processedData, 'Temperature (°C)', d => d.temperature, true, false);
    createChart(humidityChartContainer, processedData, 'Humidity (%)', d => d.humidity, true, true);
    createChart(pressureChartContainer, processedData, 'Pressure (hPa)', d => d.pressure, false, true);
  }
</script>

<div class="charts-container">
  <div class="chart">
    <!-- <h2>Temperature Comparison</h2> -->
    <div bind:this={tempChartContainer}></div>
    <!-- <h2>Humidity Comparison</h2> -->
    <div bind:this={humidityChartContainer}></div>
    <!-- <h2>Pressure Comparison</h2> -->
    <div bind:this={pressureChartContainer}></div>
  </div>
</div>

<style>
  .charts-container {
    margin-bottom: 2rem;
  }
  
  .chart {
    margin-bottom: 2rem;
    padding: 1rem;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background: white;
  }
  
  h2 {
    margin: 0 0 1rem 0;
    font-size: 1.2rem;
    color: #333;
  }
  
  .legend text {
    font-size: 12px;
  }
  
  .axis text {
    font-size: 12px;
  }
  
  .axis-label {
    font-size: 14px;
    font-weight: bold;
  }
</style>

<table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Created at</th>
        <th>MAC address</th>
        <th>Temperature</th>
        <th>Humidity</th>
        <th>Pressure</th>
      </tr>
    </thead>
    <tbody>
      {#each data.readings as reading}
      <tr>
        <td>{reading.id}</td>
        <td>{new Date(reading.created_at).toLocaleString()}</td>
        <td>{reading.mac_address}</td>
        <td>{reading.temperature}</td>
        <td>{reading.humidity}</td>
        <td>{reading.pressure}</td>
      </tr>
      {/each}
    </tbody>
  </table>