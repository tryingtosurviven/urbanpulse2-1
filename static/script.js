// static/script.js
// Dashboard interactivity and API communication for UrbanPulse demo

async function runScenario(scenarioName) {
    const statusDiv = document.getElementById('status');
    const summaryDiv = document.getElementById('summary');
    const logDiv = document.getElementById('log');

    // Update status to show loading
    statusDiv.className = 'status-running';
    statusDiv.innerText = `🔄 Running ${scenarioName.replace('_', ' ')} scenario...`;
    summaryDiv.innerHTML = '';
    logDiv.innerHTML = '<p class="log-loading">⏳ Executing agent workflow...</p>';

    try {
        // Call the backend API
        const response = await fetch(`/api/run-scenario/${scenarioName}`, { 
            method: 'POST' 
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();

        // Update status based on result
        if (data.status === 'ACTION_TAKEN') {
            statusDiv.className = 'status-alert';
            statusDiv.innerText = `🚨 ${data.status}: Health Surge Protocol Activated`;
            
            // Show detailed summary
            const risk = data.risk_assessment;
            summaryDiv.innerHTML = `
                <div class="summary-box">
                    <h3>📊 Risk Assessment</h3>
                    <p><strong>Risk Level:</strong> <span class="risk-${risk.risk_level.toLowerCase()}">${risk.risk_level}</span></p>
                    <p><strong>Current PSI:</strong> ${risk.current_psi}</p>
                    <p><strong>Predicted Surge:</strong> <span class="surge-value">+${(risk.predicted_surge * 100).toFixed(0)}%</span> patients</p>
                    <p><strong>Affected Regions:</strong> ${risk.affected_regions.join(', ') || 'None'}</p>
                </div>
                <div class="summary-box">
                    <h3>⚡ Actions Taken</h3>
                    <p><strong>Clinics Alerted:</strong> ${data.healthcare_alerts.total_clinics}</p>
                    <p><strong>Purchase Order:</strong> ${data.supply_chain_actions.po_id}</p>
                    <p><strong>Order Value:</strong> ${data.supply_chain_actions.total_value}</p>
                </div>
            `;
        } else {
            statusDiv.className = 'status-ok';
            statusDiv.innerText = `✅ ${data.status}: Air quality within safe limits`;
            
            const risk = data.risk_assessment;
            summaryDiv.innerHTML = `
                <div class="summary-box">
                    <h3>✅ All Clear</h3>
                    <p><strong>Current PSI:</strong> ${risk.current_psi}</p>
                    <p><strong>Risk Level:</strong> ${risk.risk_level}</p>
                    <p>No action required at this time. System continues monitoring.</p>
                </div>
            `;
        }

        // Display agent logs
        logDiv.innerHTML = '';
        
        if (data.logs && data.logs.length > 0) {
            data.logs.forEach(entry => {
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                
                const timestamp = new Date(entry.timestamp).toLocaleTimeString();
                
                // Create a more readable data display
                const dataStr = JSON.stringify(entry.data, null, 2);
                
                logEntry.innerHTML = `
                    <div class="log-header">
                        <span class="log-time">[${timestamp}]</span>
                        <span class="log-agent">${entry.agent}</span>
                        <span class="log-action">${entry.action}</span>
                    </div>
                    <pre class="log-data">${dataStr}</pre>
                `;
                
                logDiv.appendChild(logEntry);
            });
            
            // Auto-scroll to bottom of log
            logDiv.scrollTop = logDiv.scrollHeight;
        } else {
            logDiv.innerHTML = '<p class="log-placeholder">No logs available</p>';
        }

    } catch (error) {
        // Handle errors
        statusDiv.className = 'status-error';
        statusDiv.innerText = `❌ Error: ${error.message}`;
        
        summaryDiv.innerHTML = `
            <div class="summary-box error-box">
                <h3>⚠️ Error Occurred</h3>
                <p>Failed to execute scenario. Please check:</p>
                <ul>
                    <li>Is the backend server running?</li>
                    <li>Is the API endpoint correct?</li>
                    <li>Check browser console for details</li>
                </ul>
            </div>
        `;
        
        logDiv.innerHTML = `<p class="log-error">❌ Failed to execute scenario. Error: ${error.message}</p>`;
        
        console.error('Scenario execution error:', error);
    }
}

// Optional: Add keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Press '1' for normal scenario
    if (event.key === '1') {
        runScenario('normal');
    }
    // Press '2' for moderate haze
    else if (event.key === '2') {
        runScenario('moderate_haze');
    }
    // Press '3' for severe haze
    else if (event.key === '3') {
        runScenario('severe_haze');
    }
});

// Display keyboard shortcuts hint on page load
window.addEventListener('load', function() {
    console.log('UrbanPulse Dashboard Loaded');
    console.log('Keyboard shortcuts: Press 1, 2, or 3 to trigger scenarios');
});
