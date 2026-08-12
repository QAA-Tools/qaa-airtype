(function () {
    'use strict';

    var CHUNK_BYTES = 16 * 1024;
    var MAX_HISTORY = 25;
    var CONFIG_KEY = 'qaa_mqtt_config';
    var HISTORY_KEY = 'qaa_mqtt_history_v2';
    var DEFAULT_CONFIG = { broker: 'broker.emqx.io', port: '8084', user: '', pass: '', key: '', tls: true, enter: false };
    var HAS_WEB_CRYPTO = typeof crypto !== 'undefined' && !!crypto.subtle;

    var statusDot = document.getElementById('statusDot');
    var statusText = document.getElementById('statusText');
    var settingsBtn = document.getElementById('settingsBtn');
    var overlay = document.getElementById('overlay');
    var brokerInput = document.getElementById('brokerInput');
    var portInput = document.getElementById('portInput');
    var keyInput = document.getElementById('keyInput');
    var userInput = document.getElementById('userInput');
    var passInput = document.getElementById('passInput');
    var tlsInput = document.getElementById('tlsInput');
    var enterInput = document.getElementById('enterInput');
    var saveSettingsBtn = document.getElementById('saveSettingsBtn');
    var closeSettingsBtn = document.getElementById('closeSettingsBtn');
    var clearHistoryBtn = document.getElementById('clearHistoryBtn');
    var textInput = document.getElementById('textInput');
    var sendBtn = document.getElementById('sendBtn');
    var historyList = document.getElementById('historyList');
    var emptyTip = document.getElementById('emptyTip');
    var chatArea = document.getElementById('chatArea');

    var client = null;
    var connected = false;
    var pendingQueue = [];

    function getParams() {
        var q = new URLSearchParams(window.location.search);
        return {
            broker: q.get('b') || q.get('h') || '',
            port: q.get('p') || '',
            user: q.get('u') || '',
            pass: q.get('w') || '',
            key: q.get('k') || '',
            tls: q.get('tls') === '1'
        };
    }

    function loadConfig() {
        try {
            return JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}');
        } catch (e) {
            return {};
        }
    }

    function saveConfig(cfg) {
        try {
            localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
        } catch (e) {}
    }

    function mergeConfig() {
        var saved = loadConfig();
        var params = getParams();
        var cfg = {};
        ['broker', 'port', 'user', 'pass', 'key', 'tls', 'enter'].forEach(function (k) {
            cfg[k] = params[k] || saved[k] || DEFAULT_CONFIG[k];
        });
        saveConfig(cfg);
        return cfg;
    }

    function fillForm(cfg) {
        brokerInput.value = cfg.broker || '';
        portInput.value = cfg.port || '';
        userInput.value = cfg.user || '';
        passInput.value = cfg.pass || '';
        keyInput.value = cfg.key || '';
        tlsInput.checked = !!cfg.tls;
        enterInput.checked = !!cfg.enter;
    }

    function readForm() {
        return {
            broker: brokerInput.value.trim(),
            port: portInput.value.trim(),
            user: userInput.value.trim(),
            pass: passInput.value,
            key: keyInput.value.trim(),
            tls: tlsInput.checked,
            enter: enterInput.checked
        };
    }

    function setStatus(state, text) {
        statusText.textContent = text;
        statusDot.className = 'dot' + (state === 'connected' ? ' connected' : state === 'connecting' ? ' connecting' : state === 'error' ? ' error' : '');
    }

    function brokerUrl(cfg) {
        var b = (cfg.broker || '').trim();
        if (/^wss?:\/\//i.test(b)) return b;
        var scheme = cfg.tls ? 'wss://' : 'ws://';
        var port = (cfg.port || (cfg.tls ? '8084' : '8083')).trim();
        return scheme + b.replace(/^https?:\/\//i, '') + ':' + port + '/mqtt';
    }

    function connectMqtt() {
        if (client) {
            try { client.end(true); } catch (e) {}
            client = null;
        }
        var cfg = readForm();
        if (!cfg.broker || !cfg.key) {
            setStatus('error', '请先填写服务器和共享密钥');
            return;
        }
        saveConfig(cfg);
        var url = brokerUrl(cfg);
        setStatus('connecting', '连接中...');
        var options = {
            clientId: 'qaa-phone-' + Math.random().toString(36).slice(2, 12),
            clean: true,
            reconnectPeriod: 3000,
            connectTimeout: 10000,
            keepalive: 30
        };
        if (cfg.user) {
            options.username = cfg.user;
            options.password = cfg.pass;
        }
        client = mqtt.connect(url, options);
        client.on('connect', function () {
            connected = true;
            setStatus('connected', '已连接');
            sendBtn.disabled = false;
            flushPending();
        });
        client.on('close', function () {
            connected = false;
            setStatus('', '已断开');
            sendBtn.disabled = true;
        });
        client.on('error', function (err) {
            setStatus('error', '连接失败');
            sendBtn.disabled = true;
        });
    }

    function deriveKey(password) {
        if (HAS_WEB_CRYPTO) {
            return crypto.subtle.digest('SHA-256', new TextEncoder().encode(password)).then(function (hash) {
                return crypto.subtle.importKey('raw', hash, 'AES-GCM', false, ['encrypt']);
            });
        }
        return Promise.resolve(forge.md.sha256.create().update(password).digest().getBytes());
    }

    function bytesToBase64(bytes) {
        var binary = '';
        for (var i = 0; i < bytes.length; i += 0x8000) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        }
        return btoa(binary);
    }

    function encryptBytes(cryptoKey, bytes) {
        var iv = crypto.getRandomValues(new Uint8Array(12));
        if (HAS_WEB_CRYPTO) {
            return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, cryptoKey, bytes).then(function (ct) {
                return { iv: bytesToBase64(iv), data: bytesToBase64(new Uint8Array(ct)) };
            });
        }
        var cipher = forge.cipher.createCipher('AES-GCM', cryptoKey);
        cipher.start({ iv: forge.util.createBuffer(iv) });
        cipher.update(forge.util.createBuffer(bytes));
        cipher.finish();
        var ct = cipher.output.getBytes() + cipher.mode.tag.getBytes();
        return Promise.resolve({ iv: bytesToBase64(iv), data: btoa(ct) });
    }

    function sleep(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function topicFromKey(key) {
        var promise;
        if (HAS_WEB_CRYPTO) {
            promise = crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
        } else {
            promise = Promise.resolve(forge.md.sha256.create().update(key).digest().getBytes());
        }
        return promise.then(function (hash) {
            var hex = '';
            if (HAS_WEB_CRYPTO) {
                new Uint8Array(hash).forEach(function (b) {
                    hex += b.toString(16).padStart(2, '0');
                });
            } else {
                for (var i = 0; i < hash.length; i++) {
                    hex += hash.charCodeAt(i).toString(16).padStart(2, '0');
                }
            }
            return 'qaa/' + hex + '/in';
        });
    }

    function randomId() {
        if (crypto.randomUUID) return crypto.randomUUID();
        return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    }

    function publishPayload(payload) {
        if (!client || !connected) {
            setStatus('error', '未连接，无法发送');
            return Promise.resolve(false);
        }
        return topicFromKey(keyInput.value.trim()).then(function (topic) {
            return new Promise(function (resolve) {
                client.publish(topic, JSON.stringify(payload), { qos: 1 }, function (err) {
                    resolve(!err);
                });
            });
        });
    }

    function sendText(text, fromQueue) {
        var trimmed = text.trim();
        if (!trimmed) return Promise.resolve(false);
        if (!connected) {
            if (!fromQueue) {
                pendingQueue.push(trimmed);
                setStatus('', '已缓存 ' + pendingQueue.length + ' 条，连接后自动发送');
            }
            return Promise.resolve(true);
        }
        var enter = readForm().enter ? 1 : 0;
        return deriveKey(keyInput.value.trim()).then(function (cryptoKey) {
            var bytes = new TextEncoder().encode(trimmed);
            if (bytes.byteLength <= CHUNK_BYTES) {
                return encryptBytes(cryptoKey, bytes).then(function (enc) {
                    return publishPayload({ v: 1, t: 'text', iv: enc.iv, data: enc.data, e: enter });
                });
            }
            var id = randomId();
            var total = Math.ceil(bytes.byteLength / CHUNK_BYTES);
            var chain = Promise.resolve();
            for (var i = 0; i < total; i++) {
                (function (index) {
                    chain = chain.then(function () {
                        var part = bytes.slice(index * CHUNK_BYTES, Math.min((index + 1) * CHUNK_BYTES, bytes.byteLength));
                        return encryptBytes(cryptoKey, part).then(function (enc) {
                            return publishPayload({
                                v: 1, t: 'chunk', id: id, i: index, n: total,
                                iv: enc.iv, data: enc.data, e: enter
                            });
                        }).then(function (ok) {
                            if (!ok) return false;
                            return sleep(30);
                        });
                    });
                })(i);
            }
            return chain;
        }).then(function (ok) {
            return ok !== false;
        });
    }

    function flushPending() {
        if (!connected || pendingQueue.length === 0) return;
        var text = pendingQueue[0];
        sendText(text, true).then(function (ok) {
            if (!ok) return;
            pendingQueue.shift();
            if (pendingQueue.length) {
                flushPending();
            } else {
                setStatus('connected', '已连接');
            }
        });
    }

    function addHistory(text) {
        if (!text.trim()) return;
        var history = [];
        try {
            history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        } catch (e) {}
        var now = new Date();
        var time = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2);
        history.push({ text: text, time: time });
        if (history.length > MAX_HISTORY) history = history.slice(-MAX_HISTORY);
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {}
        renderHistory();
    }

    function renderHistory() {
        var history = [];
        try {
            history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        } catch (e) {}
        historyList.innerHTML = '';
        emptyTip.style.display = history.length ? 'none' : 'block';
        history.forEach(function (item) {
            var li = document.createElement('li');
            li.className = 'msg' + (item.text.length > 200 ? ' long' : '');
            var span = document.createElement('span');
            span.textContent = item.text;
            var time = document.createElement('span');
            time.className = 'time';
            time.textContent = item.time || '';
            li.appendChild(span);
            li.appendChild(time);
            li.addEventListener('click', function () {
                textInput.value = item.text;
                textInput.focus();
            });
            historyList.appendChild(li);
        });
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function handleSend() {
        var text = textInput.value;
        sendText(text).then(function (ok) {
            if (ok) {
                addHistory(text);
                textInput.value = '';
            }
        });
    }


    function openSettings() {
        fillForm(loadConfig());
        overlay.classList.add('show');
    }

    function closeSettings() {
        overlay.classList.remove('show');
    }

    function init() {
        var cfg = mergeConfig();
        fillForm(cfg);
        renderHistory();

        settingsBtn.addEventListener('click', openSettings);
        closeSettingsBtn.addEventListener('click', closeSettings);
        clearHistoryBtn.addEventListener('click', function () {
            localStorage.removeItem(HISTORY_KEY);
            renderHistory();
            setStatus('', '已清空聊天记录');
        });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeSettings();
        });
        saveSettingsBtn.addEventListener('click', function () {
            closeSettings();
            connectMqtt();
        });
        sendBtn.addEventListener('click', handleSend);
        textInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                handleSend();
            }
        });

        if (cfg.broker && cfg.key) {
            connectMqtt();
        } else {
            setStatus('', '未配置');
        }

        textInput.focus({ preventScroll: true });
        if (navigator.virtualKeyboard && navigator.virtualKeyboard.show) {
            try { navigator.virtualKeyboard.show(); } catch (e) {}
        }
        var activateInput = function () {
            textInput.focus();
        };
        document.addEventListener('touchend', activateInput, { once: true, passive: true });
        document.addEventListener('click', activateInput, { once: true, passive: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
