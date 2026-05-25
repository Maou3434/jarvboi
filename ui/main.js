const chatHistory = document.getElementById('chat-history');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const diagnosticLog = document.getElementById('diagnostic-log');
const connectionStatus = document.getElementById('connection-status');
const statusIndicator = document.querySelector('.status-indicator');
const aiOrb = document.getElementById('ai-orb');
const orbStatusText = document.getElementById('orb-status-text');

let socket;

function connectWebSocket() {
  // Using localhost:8000 for the FastAPI server
  socket = new WebSocket('ws://127.0.0.1:8000/ws/chat');

  socket.onopen = () => {
    connectionStatus.textContent = 'SYSTEM ONLINE';
    statusIndicator.classList.add('online');
    appendLog('SYSTEM', 'WebSocket connection established.', 'system');
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleIncomingData(data);
    } catch (e) {
      console.error('Error parsing WebSocket data:', e);
    }
  };

  socket.onclose = () => {
    connectionStatus.textContent = 'SYSTEM OFFLINE';
    statusIndicator.classList.remove('online');
    setOrbState('idle');
    appendLog('SYSTEM', 'WebSocket connection closed. Retrying in 3s...', 'system');
    setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = (error) => {
    console.error('WebSocket Error:', error);
  };
}

function handleIncomingData(data) {
  const type = data.type;
  
  if (type === 'status') {
    if (data.status === 'processing') {
      setOrbState('processing');
    } else if (data.status === 'idle') {
      setOrbState('idle');
    }
  } else if (type === 'thought') {
    appendLog('THOUGHT', data.thought, 'thought');
  } else if (type === 'tool_start') {
    const argsStr = JSON.stringify(data.tool_args);
    appendLog('TOOL EXEC', `Executing ${data.tool_name} with args: ${argsStr}`, 'tool-start');
  } else if (type === 'tool_end') {
    appendLog('TOOL RESULT', `Tool ${data.tool_name} finished.`, 'tool-end');
  } else if (type === 'final_response') {
    appendChatMessage('JARVBOI', data.response, 'assistant');
    setOrbState('idle');
  } else if (type === 'error') {
    appendLog('ERROR', data.message, 'error');
    setOrbState('idle');
  } else if (type === 'system') {
    appendLog('SYSTEM', data.message, 'system');
  }
}

function setOrbState(state) {
  if (state === 'processing') {
    aiOrb.classList.add('processing');
    orbStatusText.textContent = 'PROCESSING...';
    orbStatusText.classList.add('processing');
  } else {
    aiOrb.classList.remove('processing');
    orbStatusText.textContent = 'IDLE';
    orbStatusText.classList.remove('processing');
  }
}

function appendChatMessage(sender, text, role) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `message ${role}`;
  // Using innerHTML to allow some basic formatting, though textContent is safer.
  // For JARVIS, we keep it simple text.
  msgDiv.textContent = text;
  
  chatHistory.appendChild(msgDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function appendLog(tag, text, cssClass) {
  const logDiv = document.createElement('div');
  logDiv.className = `log-entry ${cssClass}`;
  
  const time = new Date().toLocaleTimeString([], { hour12: false });
  logDiv.innerHTML = `<span class="timestamp">[${time}]</span> <span class="tag">[${tag}]</span> ${text}`;
  
  diagnosticLog.appendChild(logDiv);
  diagnosticLog.scrollTop = diagnosticLog.scrollHeight;
}

chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  
  if (socket && socket.readyState === WebSocket.OPEN) {
    appendChatMessage('USER', text, 'user');
    socket.send(JSON.stringify({ message: text }));
    chatInput.value = '';
    setOrbState('processing');
  } else {
    appendLog('ERROR', 'Cannot send message, system offline.', 'error');
  }
});

// Init
connectWebSocket();
