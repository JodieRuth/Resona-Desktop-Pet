package com.resona.client

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.os.Binder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import okhttp3.OkHttpClient
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class ResonaService : Service() {
    companion object {
        const val ACTION_START = "com.resona.client.START"
        const val ACTION_PLAY_QUEUE = "com.resona.client.PLAY_QUEUE"
        const val ACTION_SEND_TEXT = "com.resona.client.SEND_TEXT"
        const val ACTION_START_RECORDING = "com.resona.client.START_RECORDING"
        const val ACTION_SETTINGS_UPDATE = "com.resona.client.SETTINGS_UPDATE"
        const val ACTION_SET_OUTFIT = "com.resona.client.SET_OUTFIT"
        const val ACTION_GET_OUTFITS = "com.resona.client.GET_OUTFITS"
        const val ACTION_PING = "com.resona.client.PING"
        const val ACTION_EVENT = "com.resona.client.EVENT"
        const val ACTION_STATUS = "com.resona.client.STATUS"
        const val ACTION_TRANSCRIPTION = "com.resona.client.TRANSCRIPTION"
        const val ACTION_ERROR = "com.resona.client.ERROR"
        const val ACTION_OUTFITS = "com.resona.client.OUTFITS"
        const val ACTION_OUTFIT_CHANGED = "com.resona.client.OUTFIT_CHANGED"
        const val ACTION_CONFIG = "com.resona.client.CONFIG"
        const val ACTION_PLAYBACK_STARTED = "com.resona.client.PLAYBACK_STARTED"
        const val ACTION_PLAYBACK_FINISHED = "com.resona.client.PLAYBACK_FINISHED"
        const val EXTRA_TEXT = "extra_text"
        const val EXTRA_IMAGE_URL = "extra_image_url"
        const val EXTRA_BASE_URL = "extra_base_url"
        const val EXTRA_STATE = "extra_state"
        const val EXTRA_CONFIG_JSON = "extra_config_json"
        const val EXTRA_OUTFITS_JSON = "extra_outfits_json"
        const val EXTRA_OUTFIT_ID = "extra_outfit_id"
        const val EXTRA_SETTINGS_JSON = "extra_settings_json"
        const val EXTRA_TEXT_INPUT = "extra_text_input"
        const val NOTIFICATION_CHANNEL = "resona_channel"
        const val SERVICE_NOTIFICATION_ID = 1001
        @Volatile
        private var cachedConfigJson: String = ""
        @Volatile
        private var cachedOutfitsJson: String = ""

        fun getCachedConfigJson(): String = cachedConfigJson
        fun getCachedOutfitsJson(): String = cachedOutfitsJson
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .writeTimeout(6, TimeUnit.SECONDS)
        .build()
    private var socket: ResonaWebSocket? = null
    private var baseUrl: String = ""
    private var playing = AtomicBoolean(false)
    private var mediaPlayer: MediaPlayer? = null
    private var forcePlayQueue = AtomicBoolean(false)
    private var eventNotificationId = 2000
    private val scheduler = java.util.concurrent.Executors.newSingleThreadScheduledExecutor()
    private var lastConfig: WebConfig? = null
    private var isForeground = false
    private var waitingHandshake = false
    private val binder = LocalBinder()

    inner class LocalBinder : Binder() {
        fun ping(): Boolean = true
        fun startWithUrl(url: String?): Boolean {
            startWithUrlInternal(url, "binder")
            return true
        }
    }

    override fun onBind(intent: Intent?): IBinder? {
        sendStatusBroadcast(StatusMessage("connecting", "Service onBind", null))
        return binder
    }

    override fun onCreate() {
        super.onCreate()
        sendStatusBroadcast(StatusMessage("connecting", "Service onCreate", null))
    }

    override fun onDestroy() {
        sendStatusBroadcast(StatusMessage("connecting", "Service onDestroy", null))
        socket?.close()
        mediaPlayer?.release()
        client.dispatcher.executorService.shutdown()
        scheduler.shutdown()
        super.onDestroy()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        sendStatusBroadcast(StatusMessage("connecting", "Service onStartCommand: ${action ?: "null"}", null))
        if (action == ACTION_START) {
            startWithUrlInternal(intent.getStringExtra(EXTRA_BASE_URL), "intent")
        } else if (action == ACTION_PLAY_QUEUE) {
            forcePlayQueue.set(true)
            playNextIfPossible()
        } else if (action == ACTION_SEND_TEXT) {
            val text = intent.getStringExtra(EXTRA_TEXT_INPUT) ?: ""
            if (text.isNotBlank()) {
                sendJson(org.json.JSONObject().apply {
                    put("type", "text_input")
                    put("text", text)
                })
            }
        } else if (action == ACTION_START_RECORDING) {
            sendJson(org.json.JSONObject().apply {
                put("type", "start_recording")
            })
        } else if (action == ACTION_GET_OUTFITS) {
            sendJson(org.json.JSONObject().apply {
                put("type", "get_outfits")
            })
        } else if (action == ACTION_SET_OUTFIT) {
            val outfitId = intent.getStringExtra(EXTRA_OUTFIT_ID) ?: ""
            if (outfitId.isNotBlank()) {
                sendJson(org.json.JSONObject().apply {
                    put("type", "set_outfit")
                    put("outfit_id", outfitId)
                })
            }
        } else if (action == ACTION_SETTINGS_UPDATE) {
            val settingsJson = intent.getStringExtra(EXTRA_SETTINGS_JSON) ?: ""
            if (settingsJson.isNotBlank()) {
                val payload = org.json.JSONObject()
                payload.put("type", "settings_update")
                payload.put("settings", org.json.JSONObject(settingsJson))
                sendJson(payload)
            }
        } else if (action == ACTION_PING) {
            sendStatusBroadcast(StatusMessage("ping", "Service pong", null))
        }
        return START_STICKY
    }

    private fun startWithUrlInternal(url: String?, source: String) {
        sendStatusBroadcast(StatusMessage("connecting", "startWithUrl($source)", null))
        val raw = url ?: ""
        if (raw.isNotBlank()) {
            baseUrl = normalizeBaseUrl(raw)
            ResonaPrefs.saveBaseUrl(this, baseUrl)
        } else {
            baseUrl = normalizeBaseUrl(ResonaPrefs.getBaseUrl(this))
        }
        if (baseUrl.isNotBlank()) {
            resetSocket()
            sendStatusBroadcast(StatusMessage("connecting", "Service baseUrl：$baseUrl", null))
            sendStatusBroadcast(StatusMessage("connecting", "Service 启动：$baseUrl", null))
            sendStatusBroadcast(StatusMessage("connecting", "WebSocket 连接中", null))
            probeTcp(baseUrl)
            try {
                startForegroundCompat()
            } catch (t: Throwable) {
                reportServiceError("前台启动失败：${t.message ?: "unknown"}")
            }
            ensureWebSocket()
        } else {
            reportServiceError("连接失败：地址为空")
        }
    }

    private fun probeTcp(url: String) {
        Thread {
            try {
                val uri = java.net.URI(url)
                val host = uri.host ?: return@Thread
                val port = if (uri.port > 0) uri.port else 80
                java.net.Socket().use { sock ->
                    sock.connect(java.net.InetSocketAddress(host, port), 1500)
                }
                sendStatusBroadcast(StatusMessage("connecting", "TCP 连接成功：$host:$port", null))
            } catch (t: Throwable) {
                sendStatusBroadcast(StatusMessage("connecting", "TCP 连接失败：${t::class.java.simpleName} ${t.message ?: "unknown"}", null))
            }
        }.start()
    }

    private fun ensureForeground() {
        if (!ForegroundTracker.isForeground() && !forcePlayQueue.get()) return
        if (isForeground) return
        try {
            startForegroundCompat()
        } catch (_: Exception) {
        }
    }

    private fun startForegroundCompat() {
        if (Build.VERSION.SDK_INT >= 30) {
            startForeground(SERVICE_NOTIFICATION_ID, buildServiceNotification(),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK or
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else if (Build.VERSION.SDK_INT >= 29) {
            startForeground(SERVICE_NOTIFICATION_ID, buildServiceNotification(),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            )
        } else {
            startForeground(SERVICE_NOTIFICATION_ID, buildServiceNotification())
        }
        isForeground = true
    }

 

    private fun ensureWebSocket() {
        if (socket != null) {
            sendStatusBroadcast(StatusMessage("connecting", "WebSocket 已存在", null))
            return
        }
        sendStatusBroadcast(StatusMessage("connecting", "ensureWebSocket called", null))
        val sessionId = getOrCreateSessionId()
        waitingHandshake = true
        scheduler.schedule({
            if (waitingHandshake) {
                waitingHandshake = false
                reportServiceError("连接失败：未收到握手响应")
                resetSocket()
            }
        }, 6000, java.util.concurrent.TimeUnit.MILLISECONDS)
        socket = ResonaWebSocket(
            client = client,
            baseUrl = baseUrl,
            sessionId = sessionId,
            onConnecting = { wsUrl ->
                sendStatusBroadcast(StatusMessage("connecting", "WS 准备连接：$wsUrl", null))
            },
            onOpen = { wsUrl ->
                sendStatusBroadcast(StatusMessage("connecting", "WS 已连接：$wsUrl", null))
            },
            onSpeak = { event ->
                EventQueue.enqueue(event)
                if (ForegroundTracker.isForeground()) {
                    playNextIfPossible()
                } else {
                    showEventNotification(event.text)
                }
            },
            onHandshake = { id, config ->
                ResonaPrefs.saveSessionId(this, id)
                lastConfig = config
                waitingHandshake = false
                sendStatusBroadcast(StatusMessage("connected", "握手成功", null))
                sendConfigBroadcast(config)
            },
            onStatus = { status ->
                sendStatusBroadcast(status)
            },
            onTranscription = { text ->
                val intent = Intent(ACTION_TRANSCRIPTION)
                intent.putExtra(EXTRA_TEXT, text)
                intent.setPackage(packageName)
                sendBroadcast(intent)
            },
            onError = { message ->
                waitingHandshake = false
                reportServiceError(message)
                resetSocket()
            },
            onOutfits = { outfits ->
                val json = org.json.JSONObject().apply {
                    put("pack_id", outfits.packId)
                    put("current_outfit", outfits.currentOutfit)
                    put("outfits", org.json.JSONArray().apply {
                        outfits.outfits.forEach {
                            put(org.json.JSONObject().apply {
                                put("id", it.id)
                                put("name", it.name)
                                put("is_default", it.isDefault)
                            })
                        }
                    })
                }.toString()
                cachedOutfitsJson = json
                val intent = Intent(ACTION_OUTFITS)
                intent.setPackage(packageName)
                sendBroadcast(intent)
            },
            onOutfitChanged = { change ->
                val intent = Intent(ACTION_OUTFIT_CHANGED)
                intent.putExtra(EXTRA_OUTFIT_ID, change.outfitId)
                intent.putExtra(EXTRA_IMAGE_URL, change.imageUrl)
                intent.setPackage(packageName)
                sendBroadcast(intent)
            },
            onTimerEvent = { event ->
                val delayMs = if (event.triggerAt != null) {
                    val nowSec = System.currentTimeMillis().toDouble() / 1000.0
                    Math.max(0.0, (event.triggerAt - nowSec)) * 1000.0
                } else {
                    0.0
                }
                scheduler.schedule({
                    EventQueue.enqueue(
                        SpeakEvent(
                            text = event.text,
                            audioUrl = event.audioUrl,
                            imageUrl = event.imageUrl
                        )
                    )
                    if (ForegroundTracker.isForeground()) {
                        playNextIfPossible()
                    } else {
                        showEventNotification(event.text)
                    }
                }, delayMs.toLong(), java.util.concurrent.TimeUnit.MILLISECONDS)
            },
            onConfigUpdated = { config ->
                val merged = mergeConfig(lastConfig, config)
                if (merged != null) {
                    lastConfig = merged
                    sendConfigBroadcast(merged)
                }
            }
        )
        socket?.connect()
    }

    private fun normalizeBaseUrl(input: String): String {
        val trimmed = input.trim()
        if (trimmed.isBlank()) return ""
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            trimmed.trimEnd('/')
        } else {
            "http://${trimmed.trimEnd('/')}"
        }
    }

    private fun resetSocket() {
        socket?.close()
        socket = null
        playing.set(false)
        isForeground = false
        mediaPlayer?.release()
        mediaPlayer = null
    }

    private fun playNextIfPossible() {
        if (playing.get()) return
        if (EventQueue.isEmpty()) return
        if (!ForegroundTracker.isForeground() && !forcePlayQueue.get()) return
        ensureForeground()
        val event = EventQueue.dequeue() ?: return
        forcePlayQueue.set(false)
        playing.set(true)
        sendBroadcast(Intent(ACTION_PLAYBACK_STARTED).setPackage(packageName))
        sendEventBroadcast(event)
        val audioUrl = event.audioUrl
        if (audioUrl.isNullOrBlank()) {
            val delaySec = calcUnlockDelaySeconds(event.text)
            scheduler.schedule({
                playing.set(false)
                sendBroadcast(Intent(ACTION_PLAYBACK_FINISHED).setPackage(packageName))
                playNextIfPossible()
            }, (delaySec * 1000.0).toLong(), java.util.concurrent.TimeUnit.MILLISECONDS)
            return
        }
        try {
            mediaPlayer?.release()
            mediaPlayer = MediaPlayer().apply {
                setDataSource(audioUrl)
                setOnPreparedListener { it.start() }
                setOnCompletionListener {
                    playing.set(false)
                    sendBroadcast(Intent(ACTION_PLAYBACK_FINISHED).setPackage(packageName))
                    playNextIfPossible()
                }
                setOnErrorListener { _, _, _ ->
                    playing.set(false)
                    sendBroadcast(Intent(ACTION_PLAYBACK_FINISHED).setPackage(packageName))
                    playNextIfPossible()
                    true
                }
                prepareAsync()
            }
        } catch (e: Exception) {
            playing.set(false)
            sendBroadcast(Intent(ACTION_PLAYBACK_FINISHED).setPackage(packageName))
            playNextIfPossible()
        }
    }

    private fun sendEventBroadcast(event: SpeakEvent) {
        val intent = Intent(ACTION_EVENT)
        intent.putExtra(EXTRA_TEXT, event.text)
        intent.putExtra(EXTRA_IMAGE_URL, event.imageUrl)
        intent.setPackage(packageName)
        sendBroadcast(intent)
    }

    private fun sendStatusBroadcast(status: StatusMessage) {
        val intent = Intent(ACTION_STATUS)
        intent.putExtra(EXTRA_STATE, status.state)
        if (!status.text.isNullOrBlank()) {
            intent.putExtra(EXTRA_TEXT, status.text)
        }
        if (!status.imageUrl.isNullOrBlank()) {
            intent.putExtra(EXTRA_IMAGE_URL, status.imageUrl)
        }
        intent.setPackage(packageName)
        sendBroadcast(intent)
    }

    private fun sendConfigBroadcast(config: WebConfig) {
        val json = org.json.JSONObject().apply {
            put("stt_max_duration", config.sttMaxDuration)
            put("stt_silence_threshold", config.sttSilenceThreshold)
            put("sovits_enabled", config.sovitsEnabled)
            put("text_read_speed", config.textReadSpeed)
            put("base_display_time", config.baseDisplayTime)
            put("active_pack", config.activePack)
            put("default_outfit", config.defaultOutfit)
            put("character_name", config.characterName)
            if (!config.initialImageUrl.isNullOrBlank()) {
                put("initial_image_url", config.initialImageUrl)
            }
            if (config.packMetadata != null) {
                put("pack_metadata", org.json.JSONObject().apply {
                    put("name", config.packMetadata.name)
                    put("description", config.packMetadata.description)
                    put("author", config.packMetadata.author)
                    put("version", config.packMetadata.version)
                })
            }
            put("available_packs", org.json.JSONArray().apply {
                config.availablePacks.forEach {
                    put(org.json.JSONObject().apply {
                        put("id", it.id)
                        put("name", it.name)
                        put("description", it.description)
                    })
                }
            })
        }
        cachedConfigJson = json.toString()
        val intent = Intent(ACTION_CONFIG)
        intent.putExtra(EXTRA_CONFIG_JSON, cachedConfigJson)
        intent.setPackage(packageName)
        sendBroadcast(intent)
    }

    private fun sendJson(payload: org.json.JSONObject) {
        socket?.sendJson(payload)
    }

    private fun reportServiceError(message: String) {
        val intent = Intent(ACTION_ERROR)
        intent.putExtra(EXTRA_TEXT, message)
        intent.setPackage(packageName)
        sendBroadcast(intent)
    }

    private fun mergeConfig(old: WebConfig?, update: WebConfig): WebConfig? {
        if (old == null) return update
        return WebConfig(
            sttMaxDuration = if (update.sttMaxDuration > 0) update.sttMaxDuration else old.sttMaxDuration,
            sttSilenceThreshold = if (update.sttSilenceThreshold > 0) update.sttSilenceThreshold else old.sttSilenceThreshold,
            sovitsEnabled = update.sovitsEnabled,
            textReadSpeed = if (update.textReadSpeed > 0) update.textReadSpeed else old.textReadSpeed,
            baseDisplayTime = if (update.baseDisplayTime > 0) update.baseDisplayTime else old.baseDisplayTime,
            activePack = if (update.activePack.isNotBlank()) update.activePack else old.activePack,
            defaultOutfit = if (update.defaultOutfit.isNotBlank()) update.defaultOutfit else old.defaultOutfit,
            characterName = if (update.characterName.isNotBlank()) update.characterName else old.characterName,
            initialImageUrl = update.initialImageUrl ?: old.initialImageUrl,
            packMetadata = update.packMetadata ?: old.packMetadata,
            availablePacks = if (update.availablePacks.isNotEmpty()) update.availablePacks else old.availablePacks
        )
    }

    private fun calcUnlockDelaySeconds(text: String): Double {
        val cfg = lastConfig
        val base = cfg?.baseDisplayTime ?: 2.0
        val speed = cfg?.textReadSpeed ?: 0.2
        val length = text.length
        return kotlin.math.max(1.5, base + length * speed)
    }

    private fun buildServiceNotification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(NOTIFICATION_CHANNEL, "Resona Client", NotificationManager.IMPORTANCE_LOW)
            manager.createNotificationChannel(channel)
        }
        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL)
            .setContentTitle("Resona Client")
            .setContentText("已连接，等待事件")
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setOngoing(true)
            .build()
    }

    private fun showEventNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(NOTIFICATION_CHANNEL, "Resona Client", NotificationManager.IMPORTANCE_DEFAULT)
            manager.createNotificationChannel(channel)
        }
        val intent = Intent(this, MainActivity::class.java).apply {
            action = ACTION_PLAY_QUEUE
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pending = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL)
            .setContentTitle("Resona 消息")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        manager.notify(eventNotificationId++, notification)
    }

    private fun getOrCreateSessionId(): String {
        val existing = ResonaPrefs.getSessionId(this)
        if (existing.isNotBlank()) return existing
        val id = UUID.randomUUID().toString()
        ResonaPrefs.saveSessionId(this, id)
        return id
    }
}
