// static/script.js

async function runScenario(scenarioName) {
    const logContainer = document.getElementById('log');
    const statusDiv = document.getElementById('status');
    const summaryDiv = document.getElementById('summary');

    // 1. Update UI to "Running"
    statusDiv.className = 'status-running';
    statusDiv.innerText = `🤖 Agents Coordinating: ${scenarioName.replace('_', ' ')}...`;
    logContainer.innerHTML = '<p class="log-loading">Agents are processing data and calculating surge risks...</p>';

    try {
        const res = await fetch(`/api/run-scenario/${scenarioName}`, { method: "POST" });
        const data = await res.json();

        if (!res.ok) throw new Error(data.error || "Failed to run");

        // 2. Update Status
        statusDiv.className = 'status-ok';
        statusDiv.innerText = "✅ Action Protocol Executed";

        // 3. Display AI Summary
        const risk = data.risk_assessment;
        summaryDiv.innerHTML = `
            <div class="summary-box">
                <p><strong>Highest PSI:</strong> ${risk.current_psi} (${risk.risk_level})</p>
                <p><strong>Affected:</strong> ${risk.affected_regions.join(', ')}</p>
                <p><strong>Action:</strong> ${data.healthcare_alerts.alert_message}</p>
            </div>
        `;

        // 4. Update Logs to look "Agentic"
        logContainer.innerHTML = ''; // Clear loading
        addLogEntry("EnvironmentSentinel", "Triggered Health Surge Protocol", risk);
        addLogEntry("SupplyChainAgent", "Authorized Inventory Push", data.supply_chain_actions);

    } catch (e) {
        statusDiv.className = 'status-error';
        statusDiv.innerText = "❌ System Error";
        logContainer.innerHTML = `<p class="log-error">${e.message}</p>`;
    }
}

function addLogEntry(agent, action, data) {
    const logContainer = document.getElementById('log');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <div class="log-header">
            <span class="log-time">${new Date().toLocaleTimeString()}</span>
            <span class="log-agent">${agent}</span>
            <span class="log-action">${action}</span>
        </div>
        <pre class="log-data">${JSON.stringify(data, null, 2)}</pre>
    `;
    logContainer.prepend(entry);
}