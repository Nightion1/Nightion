document.addEventListener('DOMContentLoaded', async () => {
    await fetchIndex();
});

const API_BASE = 'http://localhost:8000';

async function fetchIndex() {
    try {
        const res = await fetch(`${API_BASE}/api/logs/index`);
        const traces = await res.json();
        
        const listDiv = document.getElementById('index-list');
        listDiv.innerHTML = '';
        
        traces.reverse().forEach(trace => {
            const item = document.createElement('div');
            item.className = 'trace-list-item';
            
            let statusClass = 'status-pending';
            if(trace.status === 'ok') statusClass = 'status-ok';
            if(trace.status === 'failed') statusClass = 'status-failed';
            if(trace.status === 'blocked') statusClass = 'status-blocked';
            
            const timestamp = new Date(trace.timestamp).toLocaleString();
            
            item.innerHTML = `
                <div style="font-size: 0.8em; color: #94a3b8;">${timestamp}</div>
                <div style="font-weight: bold; margin: 4px 0;">${trace.trace_id.substring(0,8)}...</div>
                <div style="font-size: 0.9em; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${trace.query || 'No query tracked'}</div>
                <div class="${statusClass}" style="margin-top: 6px; font-size: 0.8em; text-transform: uppercase;">${trace.status}</div>
            `;
            
            item.onclick = (e) => {
                document.querySelectorAll('.trace-list-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
                renderTraceDetails(trace.trace_id);
            };
            
            listDiv.appendChild(item);
        });
    } catch (e) {
        document.getElementById('index-list').innerHTML = `<div class="status-failed">Failed to load index.json: ${e.message}</div>`;
    }
}

async function fetchLogArtifact(trace_id, artifact) {
    try {
        const res = await fetch(`${API_BASE}/api/logs/${trace_id}/${artifact}`);
        if(!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

async function renderTraceDetails(trace_id) {
    document.getElementById('trace-title').innerText = `Trace: ${trace_id}`;
    const content = document.getElementById('trace-content');
    content.innerHTML = '<div style="color: #94a3b8;">Loading execution tree...</div>';
    
    // Fetch all possible artifacts concurrently
    const [request, router, plan, tool_runs, response] = await Promise.all([
        fetchLogArtifact(trace_id, 'request.json'),
        fetchLogArtifact(trace_id, 'router.json'),
        fetchLogArtifact(trace_id, 'plan.json'),
        fetchLogArtifact(trace_id, 'tool_runs.json'),
        fetchLogArtifact(trace_id, 'response.json')
    ]);
    
    let html = '';
    
    if(request) {
        html += `<div class="block-card"><h3>1. Raw Request Intent</h3>
        <div class="code-block">${request.query}</div></div>`;
    }
    
    if(router) {
        html += `<div class="block-card"><h3>2. Semantic Routing</h3>
        <span class="badge">Intent: ${router.intent}</span>
        <span class="badge">Confidence: ${(router.confidence * 100).toFixed(1)}%</span>
        <p style="color: #94a3b8; margin-top: 10px;">${router.reasoning}</p></div>`;
    }
    
    if(plan && plan.length > 0) {
        html += `<div class="block-card"><h3>3. Cognitive Planning (Iterations: ${plan.length})</h3>`;
        plan.forEach((iteration, idx) => {
            html += `<div style="border-left: 2px solid #334155; padding-left: 1rem; margin-bottom: 1rem;">
                <span class="badge" style="background: #475569;">Iteration ${idx + 1}</span>
                <span class="badge">Strategy: ${iteration.context_strategy}</span>
                <span class="badge">Uncertainty: ${(iteration.uncertainty * 100).toFixed(1)}%</span>
                <p><strong>Goal:</strong> ${iteration.understanding}</p>
                <div class="code-block">${JSON.stringify(iteration.steps, null, 2)}</div>
            </div>`;
        });
        html += `</div>`;
    }
    
    if(tool_runs && tool_runs.length > 0) {
        html += `<div class="block-card"><h3>4. Sandbox Execution Traces</h3>`;
        tool_runs.forEach((run, idx) => {
            const statusColor = run.verification_decision === 'fail' ? '#ef4444' : (run.verification_decision === 'uncertain' ? '#f59e0b' : '#10b981');
            html += `<div style="margin-bottom: 1rem; background: #0f172a; padding: 1rem; border-radius: 6px; border-left: 4px solid ${statusColor};">
                <strong>Step:</strong> ${run.step} <br>
                <strong>Verifier Output:</strong> <span style="color: ${statusColor}">${run.verification_decision || 'N/A'}</span> <br>
                ${run.verification_reason ? `<em style="color:#94a3b8;">Reason: ${run.verification_reason}</em><br>` : ''}
                ${run.suggested_fix ? `<strong style="color: #f59e0b;">Required Fix:</strong> ${run.suggested_fix}<br>` : ''}
                <div class="code-block" style="margin-top: 10px;">${run.tool_output || 'No output captured'}</div>
            </div>`;
        });
        html += `</div>`;
    }
    
    if(response) {
        const respColor = response.status === 'ok' ? '#10b981' : (response.status === 'blocked' ? '#f59e0b' : '#ef4444');
        html += `<div class="block-card" style="border-left-color: ${respColor}"><h3>5. Terminal Policy Result</h3>
        <span class="badge" style="background: ${respColor}">${response.status}</span>
        <div class="code-block" style="margin-top: 10px;">${response.result}</div></div>`;
    }
    
    content.innerHTML = html || '<div class="status-failed">Trace payload disjointed or missing offline securely.</div>';
}
