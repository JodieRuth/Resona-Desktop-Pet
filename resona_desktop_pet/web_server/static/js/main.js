console.log('[WEB] main.js loaded', window.__RES_WEB_VERSION || '');
if (window.__clientLog) {
    window.__clientLog("info", "main.js loaded", { version: window.__RES_WEB_VERSION || "" });
}
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

let socket;
let sessionId = localStorage.getItem('resona_session_id');
let packId = localStorage.getItem('resona_pack_id') || 'default';
let currentConfig = {};
const scheduledTimerEvents = new Map();

const statusIndicator = document.getElementById('status-indicator');
const characterImg = document.getElementById('character-img');
const characterNameEl = document.getElementById('character-name');
const audioPlayer = document.getElementById('audio-player');
const micBtn = document.getElementById('mic-btn');
const sendBtn = document.getElementById('send-btn');
const textInput = document.getElementById('text-input');
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeSettingsBtn = document.getElementById('close-settings-btn');

const settingPackId = document.getElementById('setting-pack-id');
const packSelect = document.createElement('select');
packSelect.id = 'pack-select';
packSelect.style.padding = '5px';
packSelect.style.borderRadius = '5px';
packSelect.style.border = '1px solid #ccc';
packSelect.style.marginLeft = '10px';

if (settingPackId) {
    settingPackId.innerHTML = '';
    settingPackId.appendChild(packSelect);
}

packSelect.addEventListener('change', (e) => {
    const newPackId = e.target.value;
    if (newPackId && newPackId !== currentConfig.active_pack) {
        if (confirm(`Switch to pack "${newPackId}"? This may take a few seconds.`)) {
            socket.send(JSON.stringify({
                type: 'settings_update',
                settings: {
                    active_pack: newPackId
                }
            }));
            statusIndicator.className = 'status-dot busy';
        } else {
            e.target.value = currentConfig.active_pack;
        }
    }
});

const settingCharName = document.getElementById('setting-char-name');
const settingOutfit = document.getElementById('setting-outfit');
const outfitSelect = document.createElement('select');
outfitSelect.id = 'outfit-select';
outfitSelect.style.padding = '5px';
outfitSelect.style.borderRadius = '5px';
outfitSelect.style.border = '1px solid #ccc';
outfitSelect.style.marginLeft = '10px';

if (settingOutfit) {
    settingOutfit.innerHTML = '';
    settingOutfit.appendChild(outfitSelect);
}

outfitSelect.addEventListener('change', (e) => {
    const newOutfitId = e.target.value;
    if (newOutfitId) {
        socket.send(JSON.stringify({
            type: 'set_outfit',
            outfit_id: newOutfitId
        }));
    }
});

const settingDesc = document.getElementById('setting-desc');
const settingAuthor = document.getElementById('setting-author');
const settingVersion = document.getElementById('setting-version');

let isRecording = false;
let isInitializingRecording = false;
let mediaRecorder;
let audioChunks = [];
let finalizeTimer;
let isFinalizingRecording = false;
let isSpeaking = false;
let speakUnlockTimer;
let lastIdleImageUrl = null;

function connect() {
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        console.log('[WS] Connected');
        statusIndicator.className = 'status-dot connected';
        socket.send(JSON.stringify({
            type: 'handshake',
            session_id: sessionId,
            pack_id: packId
        }));
    };

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log('[WS] Message', msg.type, msg);
        handleMessage(msg);
    };

    socket.onclose = () => {
        console.log('[WS] Disconnected');
        statusIndicator.className = 'status-dot disconnected';
        setTimeout(connect, 3000);
    };
    
    socket.onerror = (err) => {
        console.error('WebSocket error:', err);
        statusIndicator.className = 'status-dot disconnected';
    };
}

function lockInput() {
    textInput.disabled = true;
    sendBtn.disabled = true;
    micBtn.disabled = true;
}

function unlockInput() {
    textInput.disabled = false;
    sendBtn.disabled = false;
    micBtn.disabled = false;
    textInput.focus();
}

function calcUnlockDelaySeconds(text, duration) {
    if (duration && duration > 0) return duration;
    const base = currentConfig.base_display_time ?? 2.0;
    const speed = currentConfig.text_read_speed ?? 0.2;
    return Math.max(1.5, base + String(text || '').length * speed);
}

function finishSpeaking() {
    isSpeaking = false;
    if (speakUnlockTimer) clearTimeout(speakUnlockTimer);
    if (lastIdleImageUrl) characterImg.src = lastIdleImageUrl;
    textInput.value = '';
    unlockInput();
}

function formatTimestamp(tsSeconds) {
    if (!tsSeconds) return '';
    const date = new Date(tsSeconds * 1000);
    return date.toLocaleTimeString();
}

function playTimerTask(task) {
    const text = task.text_display || task.text_tts || "Time's up!";
    textInput.value = text;
    isSpeaking = true;
    lockInput();

    if (task.image_url) {
        characterImg.src = task.image_url;
    }

    const unlockDelaySec = calcUnlockDelaySeconds(text, task.duration);
    if (speakUnlockTimer) clearTimeout(speakUnlockTimer);

    if (task.audio_url) {
        audioPlayer.onended = () => finishSpeaking();
        audioPlayer.onerror = () => finishSpeaking();
        audioPlayer.src = task.audio_url;
        audioPlayer.play().catch(() => finishSpeaking());
        const fallbackDelay = task.duration && task.duration > 0 ? (task.duration + 0.5) : Math.max(unlockDelaySec, 10);
        speakUnlockTimer = setTimeout(() => finishSpeaking(), fallbackDelay * 1000);
    } else {
        speakUnlockTimer = setTimeout(() => finishSpeaking(), unlockDelaySec * 1000);
    }
}

function scheduleTimerTask(msg) {
    const task = msg.task || {};
    const triggerAt = msg.trigger_at || task.due_at;
    const taskId = task.id || `${triggerAt || ''}-${task.text_display || task.text_tts || ''}`;
    if (scheduledTimerEvents.has(taskId)) return;

    const nowSec = Date.now() / 1000;
    const delayMs = Math.max(0, ((triggerAt || nowSec) - nowSec) * 1000);
    const timeoutId = setTimeout(() => {
        scheduledTimerEvents.delete(taskId);
        playTimerTask(task);
    }, delayMs);

    scheduledTimerEvents.set(taskId, timeoutId);
}

function handleMessage(msg) {
    if (msg.type === 'handshake_ack') {
        sessionId = msg.session_id;
        localStorage.setItem('resona_session_id', sessionId);
        currentConfig = msg.config || {};
        
        updateCharacter(currentConfig);
        updateSettingsUI(currentConfig);
        

        socket.send(JSON.stringify({ type: 'get_outfits' }));
        
        console.log('Session initialized:', sessionId);
    } else if (msg.type === 'outfits_list') {
        if (outfitSelect && msg.outfits) {
            outfitSelect.innerHTML = '';
            msg.outfits.forEach(outfit => {
                const option = document.createElement('option');
                option.value = outfit.id;
                option.textContent = outfit.name || outfit.id;
                if (outfit.id === msg.current_outfit) {
                    option.selected = true;
                }
                outfitSelect.appendChild(option);
            });
        }
    } else if (msg.type === 'outfit_changed') {
        if (msg.image_url) {
            characterImg.src = msg.image_url;
        }
        if (outfitSelect) {
            outfitSelect.value = msg.outfit_id;
        }
    } else if (msg.type === 'status') {
                if (msg.state === 'thinking') {
                    textInput.value = msg.text || "Thinking...";
                    textInput.disabled = true;
                    sendBtn.disabled = true;
                    micBtn.disabled = true;
                    
                    statusIndicator.className = 'status-dot thinking'; 
                    if (msg.image_url) characterImg.src = msg.image_url;
                } else if (msg.state === 'listening') {
                    statusIndicator.className = isRecording ? 'status-dot recording' : 'status-dot busy';
                    if (msg.text) textInput.value = msg.text;
                    
                    textInput.disabled = true;
                    sendBtn.disabled = true;
                    micBtn.disabled = false;
                    
                    if (msg.image_url) characterImg.src = msg.image_url;
                } else if (msg.state === 'busy') {
                    statusIndicator.className = 'status-dot busy';
                    lockInput();
                } else {
                    statusIndicator.className = 'status-dot connected';
                    if (msg.image_url) {
                        lastIdleImageUrl = msg.image_url;
                        if (!isSpeaking) characterImg.src = msg.image_url;
                    }
                    if (!isSpeaking) unlockInput();
                }
            } else if (msg.type === 'speak') {
                textInput.value = msg.text;
                isSpeaking = true;
                lockInput();
                
                if (msg.image_url) {
                    characterImg.src = msg.image_url;
                }
                
                const unlockDelaySec = calcUnlockDelaySeconds(msg.text, msg.duration);
                if (speakUnlockTimer) clearTimeout(speakUnlockTimer);
                
                if (msg.audio_url) {
                    audioPlayer.onended = () => finishSpeaking();
                    audioPlayer.onerror = () => finishSpeaking();
                    audioPlayer.src = msg.audio_url;
                    audioPlayer.play().catch(() => finishSpeaking());
                    const fallbackDelay = msg.duration && msg.duration > 0 ? (msg.duration + 0.5) : Math.max(unlockDelaySec, 10);
                    speakUnlockTimer = setTimeout(() => finishSpeaking(), fallbackDelay * 1000);
                } else {
                    speakUnlockTimer = setTimeout(() => finishSpeaking(), unlockDelaySec * 1000);
                }
            } else if (msg.type === 'transcription') {
                textInput.value = msg.text;
            } else if (msg.type === 'timer_event') {
                scheduleTimerTask(msg);
            } else if (msg.type === 'error') {
                textInput.value = `Error: ${msg.message}`;
                statusIndicator.className = (socket && socket.readyState === WebSocket.OPEN) ? 'status-dot connected' : 'status-dot disconnected';
                textInput.disabled = false;
                sendBtn.disabled = false;
                micBtn.disabled = false;
            }
}

function updateCharacter(config) {
    if (config.initial_image_url) {
        characterImg.src = config.initial_image_url;
    } else if (config.active_pack && config.default_outfit) {
        const spritePath = `/packs/${config.active_pack}/assets/sprites/${config.default_outfit}/000.png`;
        characterImg.src = spritePath;
        characterImg.onerror = () => {
            console.warn("Failed to load character sprite at", spritePath);
            const altPath = `/packs/${config.active_pack}/assets/sprites/${config.default_outfit}/0000.png`;
            if (characterImg.src !== window.location.origin + altPath) {
                characterImg.src = altPath;
            }
        };
    }
    
    if (config.character_name) {
        characterNameEl.textContent = config.character_name;
    }
}

function updateSettingsUI(config) {
    if (packSelect && config.available_packs) {
        packSelect.innerHTML = ''; 
        config.available_packs.forEach(pack => {
            const option = document.createElement('option');
            option.value = pack.id;
            option.textContent = pack.name || pack.id;
            if (pack.id === config.active_pack) {
                option.selected = true;
            }
            packSelect.appendChild(option);
        });
    } else if (packSelect && config.active_pack) {
         if (packSelect.options.length === 0) {
             const option = document.createElement('option');
             option.value = config.active_pack;
             option.textContent = config.active_pack;
             packSelect.appendChild(option);
         }
         packSelect.value = config.active_pack;
    }

    if (settingCharName) settingCharName.textContent = config.character_name || 'Unknown';
    
    if (config.pack_metadata) {
        if (settingDesc) settingDesc.textContent = config.pack_metadata.description || 'No description';
        if (settingAuthor) settingAuthor.textContent = config.pack_metadata.author || 'Unknown';
        if (settingVersion) settingVersion.textContent = config.pack_metadata.version || '0.0.0';
    }
}



function showDialog(text, duration = 0) {
    console.log("showDialog called but deprecated:", text);
}


let maxRecordingTimeMs = 60000; 
let silenceThreshold = 1.0;     
let recordingTimeout;
let silenceTimer;
let audioContext;
let analyser;
let microphone;
let javascriptNode;

micBtn.addEventListener('click', async () => {
    if (isInitializingRecording) return;
    
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
});

function setupSilenceDetection(stream) {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    microphone = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    microphone.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    
    const checkInterval = 100;
    let silenceStart = Date.now();
    
    const VOLUME_THRESHOLD = 15; 

    if (window.silenceInterval) clearInterval(window.silenceInterval);

    window.silenceInterval = setInterval(() => {
        if (!isRecording) {
            clearInterval(window.silenceInterval);
            return;
        }

        analyser.getByteFrequencyData(dataArray);
        
        let sum = 0;
        for(let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        let average = sum / bufferLength;


        if (average > VOLUME_THRESHOLD) {
            silenceStart = Date.now();
        } else {
            const silenceDuration = (Date.now() - silenceStart) / 1000;
            if (silenceDuration > silenceThreshold) {
                console.log(`Silence detected for ${silenceDuration}s, stopping recording...`);
                clearInterval(window.silenceInterval);
                stopRecording();
            }
        }
    }, checkInterval);
}

async function startRecording() {
    if (isInitializingRecording) return;
    isInitializingRecording = true;
    micBtn.disabled = true; 
    
    try {
        console.log('[REC] startRecording');
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('[REC] getUserMedia ok');
        
        if (audioContext && audioContext.state === 'suspended') {
            await audioContext.resume();
        }
        
        const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? { mimeType: 'audio/webm;codecs=opus' } : {};
        mediaRecorder = new MediaRecorder(stream, options);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                audioChunks.push(e.data);
                console.log('[REC] dataavailable', e.data.size);
            }
        };

        mediaRecorder.onstop = finalizeRecording;

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        statusIndicator.className = 'status-dot recording';
        
        if (currentConfig.stt_max_duration) {
            maxRecordingTimeMs = currentConfig.stt_max_duration * 1000;
        }
        if (currentConfig.stt_silence_threshold) {
            silenceThreshold = currentConfig.stt_silence_threshold;
        }

        console.log(`[REC] Recording started. Max: ${maxRecordingTimeMs}ms, Silence: ${silenceThreshold}s`);
        
        textInput.value = "Listening...";
        textInput.disabled = true;
        sendBtn.disabled = true;

        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log('[REC] start_recording -> ws');
            socket.send(JSON.stringify({ type: 'start_recording' }));
        }

        recordingTimeout = setTimeout(() => {
            if (isRecording) {
                console.log("Max recording time reached, stopping...");
                stopRecording();
            }
        }, maxRecordingTimeMs);
        
        setupSilenceDetection(stream);
        
    } catch (err) {
        console.error('Error accessing microphone:', err);
        alert('Could not access microphone');
    } finally {
        isInitializingRecording = false;
        micBtn.disabled = false;
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        console.log('[REC] stopRecording');
        if (recordingTimeout) clearTimeout(recordingTimeout);
        if (window.silenceInterval) clearInterval(window.silenceInterval);
        try {
            mediaRecorder.requestData();
        } catch (e) {}
        mediaRecorder.stop();
    }
    
    isRecording = false;
    micBtn.classList.remove('recording');
    textInput.value = "Processing..."; 
    
    if (mediaRecorder) {
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
}

function finalizeRecording() {
    if (finalizeTimer) clearTimeout(finalizeTimer);
    if (isFinalizingRecording) return;
    isFinalizingRecording = true;
    console.log('[REC] finalizeRecording', audioChunks.length);
    finalizeTimer = setTimeout(() => {
        if (audioChunks.length === 0) {
            textInput.value = "Error: No audio data captured";
            statusIndicator.className = (socket && socket.readyState === WebSocket.OPEN) ? 'status-dot connected' : 'status-dot disconnected';
            textInput.disabled = false;
            sendBtn.disabled = false;
            micBtn.disabled = false;
            isFinalizingRecording = false;
            return;
        }
        uploadAudio();
    }, 100);
}

async function uploadAudio() {
    const mimeType = mediaRecorder.mimeType; 
    const audioBlob = new Blob(audioChunks, { type: mimeType });
    const formData = new FormData();
    
    const ext = mimeType.includes('wav') ? 'wav' : 'webm';
    formData.append('file', audioBlob, `recording.${ext}`);
    formData.append('session_id', sessionId);

    try {
        console.log(`[REC] Uploading audio... Size: ${audioBlob.size}, Type: ${mimeType}`);
        const response = await fetch('/upload_audio', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            let errorMessage = 'Upload failed';
            try {
                const data = await response.json();
                if (data && data.error) errorMessage = data.error;
            } catch (e) {}
            throw new Error(errorMessage);
        }
        console.log('[REC] Audio uploaded successfully');
        isFinalizingRecording = false;
    } catch (err) {
        console.error("Audio upload error:", err);
        statusIndicator.className = (socket && socket.readyState === WebSocket.OPEN) ? 'status-dot connected' : 'status-dot disconnected';
        textInput.value = `Error uploading audio: ${err.message || err}`;
        textInput.disabled = false;
        sendBtn.disabled = false;
        micBtn.disabled = false;
        isFinalizingRecording = false;
    }
}

function sendText() {
    const text = textInput.value.trim();
    if (text) {
        socket.send(JSON.stringify({
            type: 'text_input',
            text: text
        }));
        textInput.disabled = true;
        sendBtn.disabled = true;
        micBtn.disabled = true;
    }
}

sendBtn.addEventListener('click', sendText);
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendText();
});

if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
        settingsModal.classList.remove('hidden');
    });
}

if (closeSettingsBtn) {
    closeSettingsBtn.addEventListener('click', () => {
        settingsModal.classList.add('hidden');
    });
}

if (settingsModal) {
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            settingsModal.classList.add('hidden');
        }
    });
}

connect();
