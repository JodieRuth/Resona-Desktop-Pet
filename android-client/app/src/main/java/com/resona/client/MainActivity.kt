package com.resona.client

import android.Manifest
import android.app.ActivityManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.text.InputType
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import org.json.JSONObject
import java.io.File
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : AppCompatActivity() {
    private lateinit var imageView: TransparentCropImageView
    private lateinit var dialogueView: TextView
    private lateinit var statusView: TextView
    private lateinit var statusDot: View
    private lateinit var characterNameView: TextView
    private lateinit var textInput: EditText
    private lateinit var micBtn: Button
    private lateinit var sendBtn: Button
    private lateinit var settingsBtn: Button
    private lateinit var connectBtn: Button
    private lateinit var dialogueBox: View
    private lateinit var connectLogOverlay: View
    private lateinit var connectLogText: TextView
    private val httpClient = OkHttpClient()
    private val probeClient = OkHttpClient.Builder()
        .callTimeout(6, TimeUnit.SECONDS)
        .connectTimeout(6, TimeUnit.SECONDS)
        .build()
    private val discovering = AtomicBoolean(false)
    private var discoveryThread: Thread? = null
    private var currentConfig: WebConfig? = null
    private var outfits: List<OutfitInfo> = emptyList()
    private var isSpeaking = false
    private var isRecording = false
    private var currentState = "idle"
    private var lastIdleImageUrl: String? = null
    private var lastOutfitChangeAt: Long = 0L
    private val imageLoadToken = AtomicInteger(0)
    private var recorder: AudioRecorder? = null
    private val connectLogBuffer = StringBuilder()
    private var connectLogVisible = false
    private var gotConfig = false
    private var gotOutfits = false
    private var receiverRegistered = false
    private var discoveryToken = 0
    private var discoveryFound = false
    private var lastServicePongAt = 0L
    private var serviceConnection: ServiceConnection? = null
    private var serviceBound = false
    private var pendingServiceUrl: String? = null
    private var connectLogEnabled = false
    private var pendingResponse = false

    private val eventReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                ResonaService.ACTION_EVENT -> {
                    val text = intent.getStringExtra(ResonaService.EXTRA_TEXT) ?: ""
                    val imageUrl = intent.getStringExtra(ResonaService.EXTRA_IMAGE_URL) ?: ""
                    if (text.isNotBlank()) {
                        showDisplayText(text)
                    }
                    if (imageUrl.isNotBlank()) {
                        loadImage(imageUrl)
                    }
                }
                ResonaService.ACTION_STATUS -> {
                    val state = intent.getStringExtra(ResonaService.EXTRA_STATE) ?: "idle"
                    val text = intent.getStringExtra(ResonaService.EXTRA_TEXT)
                    val imageUrl = intent.getStringExtra(ResonaService.EXTRA_IMAGE_URL)
                    appendConnectLog("状态：$state ${text ?: ""}".trim())
                    if (state == "ping" || text == "Service pong") {
                        lastServicePongAt = System.currentTimeMillis()
                    }
                    if (!(state == "connecting" && (gotConfig || gotOutfits))) {
                        handleStatus(state, text, imageUrl)
                    }
                }
                ResonaService.ACTION_TRANSCRIPTION -> {
                    val text = intent.getStringExtra(ResonaService.EXTRA_TEXT) ?: ""
                    if (text.isNotBlank()) {
                        if (textInput.visibility == View.VISIBLE) {
                            textInput.setText(text)
                        } else {
                            dialogueView.text = text
                        }
                    }
                }
                ResonaService.ACTION_ERROR -> {
                    val text = intent.getStringExtra(ResonaService.EXTRA_TEXT) ?: "未知错误"
                    appendConnectLog("错误：$text")
                    reportClientError(text)
                }
                ResonaService.ACTION_OUTFITS -> {
                    val json = intent.getStringExtra(ResonaService.EXTRA_OUTFITS_JSON)
                        ?: ResonaService.getCachedOutfitsJson()
                    if (json.isBlank()) return
                    val obj = JSONObject(json)
                    val list = obj.optJSONArray("outfits")
                    val out = mutableListOf<OutfitInfo>()
                    if (list != null) {
                        for (i in 0 until list.length()) {
                            val o = list.optJSONObject(i) ?: continue
                            out.add(
                                OutfitInfo(
                                    id = o.optString("id"),
                                    name = o.optString("name", o.optString("id")),
                                    isDefault = o.optBoolean("is_default", false)
                                )
                            )
                        }
                    }
                    outfits = out
                    gotOutfits = true
                    appendConnectLog("服装列表：${outfits.size}")
                    if (gotConfig) {
                        onConnectionReady()
                    }
                }
                ResonaService.ACTION_OUTFIT_CHANGED -> {
                    val imageUrl = intent.getStringExtra(ResonaService.EXTRA_IMAGE_URL)
                    if (!imageUrl.isNullOrBlank()) {
                        loadImage(imageUrl)
                        lastIdleImageUrl = imageUrl
                        lastOutfitChangeAt = System.currentTimeMillis()
                    }
                }
                ResonaService.ACTION_CONFIG -> {
                    val json = intent.getStringExtra(ResonaService.EXTRA_CONFIG_JSON)
                        ?: ResonaService.getCachedConfigJson()
                    if (json.isBlank()) return
                    val previousPackId = currentConfig?.activePack
                    currentConfig = parseConfig(json)
                    val cfg = currentConfig
                    if (cfg != null) {
                        characterNameView.text = cfg.characterName
                        statusView.text = "已连接"
                        appendConnectLog("配置：角色=${cfg.characterName}")
                        if (!previousPackId.isNullOrBlank() && cfg.activePack != previousPackId) {
                            lastIdleImageUrl = null
                        }
                        if (lastIdleImageUrl.isNullOrBlank() && !cfg.initialImageUrl.isNullOrBlank()) {
                            loadImage(cfg.initialImageUrl)
                        }
                        requestOutfits()
                        gotConfig = true
                        if (gotOutfits) {
                            onConnectionReady()
                        }
                    }
                }
                ResonaService.ACTION_PLAYBACK_STARTED -> {
                    isSpeaking = true
                    if (textInput.visibility == View.VISIBLE) {
                        showDisplayText(textInput.text.toString().trim())
                        textInput.setText("")
                    }
                    lockAllInput()
                }
                ResonaService.ACTION_PLAYBACK_FINISHED -> {
                    isSpeaking = false
                    finishPendingResponse()
                    if (!lastIdleImageUrl.isNullOrBlank()) {
                        loadImage(lastIdleImageUrl!!)
                    }
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        try {
            imageView = findViewById(R.id.characterImage)
            dialogueView = findViewById(R.id.dialogueText)
            statusView = findViewById(R.id.statusText)
            statusDot = findViewById(R.id.statusDot)
            characterNameView = findViewById(R.id.characterName)
            textInput = findViewById(R.id.textInput)
            micBtn = findViewById(R.id.micBtn)
            sendBtn = findViewById(R.id.sendBtn)
            settingsBtn = findViewById(R.id.settingsBtn)
            connectBtn = findViewById(R.id.connectBtn)
            dialogueBox = findViewById(R.id.dialogueBox)
            connectLogOverlay = findViewById(R.id.connectLogOverlay)
            connectLogText = findViewById(R.id.connectLogText)
            updateStatusDot("disconnected")
            registerEventReceiverIfNeeded()
        } catch (t: Throwable) {
            val summary = "${t::class.java.simpleName}: ${t.message ?: "unknown"}"
            try {
                val status = findViewById<TextView>(R.id.statusText)
                val dialog = findViewById<TextView>(R.id.dialogueText)
                status.text = "启动失败"
                dialog.text = ""
                showErrorPopup("Error: $summary")
                updateStatusDot("disconnected")
            } catch (_: Throwable) {
            }
            return
        }

        val savedUrl = normalizeBaseUrl(ResonaPrefs.getBaseUrl(this))
        if (savedUrl.isNotBlank()) {
            startConnection(savedUrl, "自动连接")
        } else {
            startDiscovery()
        }

        sendBtn.setOnClickListener {
            val text = textInput.text.toString().trim()
            if (text.isNotBlank()) {
                sendText(text)
            }
        }

        textInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_SEND ||
                actionId == android.view.inputmethod.EditorInfo.IME_ACTION_DONE
            ) {
                val text = textInput.text.toString().trim()
                if (text.isNotBlank()) {
                    sendText(text)
                }
                true
            } else {
                false
            }
        }

        micBtn.setOnClickListener {
            if (!isRecording) {
                startRecording()
            } else {
                stopRecording()
            }
        }

        settingsBtn.setOnClickListener {
            showSettingsDialog()
        }

        connectBtn.setOnClickListener {
            showManualConnectDialog("手动连接")
        }

        try {
            requestPermissionsIfNeeded()
        } catch (t: Throwable) {
            reportClientError("权限初始化失败：${t.message ?: "unknown"}")
        }
    }

    override fun onResume() {
        super.onResume()
        registerEventReceiverIfNeeded()
        requestPlayQueue()
    }

    override fun onPause() {
        super.onPause()
    }

    override fun onDestroy() {
        unregisterEventReceiverIfNeeded()
        if (serviceBound) {
            serviceConnection?.let {
                try {
                    unbindService(it)
                } catch (_: Exception) {
                }
            }
        }
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == ResonaService.ACTION_PLAY_QUEUE) {
            requestPlayQueue()
        }
    }

    private fun sendText(text: String) {
        markRequestSubmitted(text)
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_SEND_TEXT
            putExtra(ResonaService.EXTRA_TEXT_INPUT, text)
        }
        startService(intent)
    }

    private fun requestOutfits() {
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_GET_OUTFITS
        }
        startService(intent)
    }

    private fun setOutfit(outfitId: String) {
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_SET_OUTFIT
            putExtra(ResonaService.EXTRA_OUTFIT_ID, outfitId)
        }
        startService(intent)
    }

    private fun setActivePack(packId: String) {
        val settings = JSONObject().apply {
            put("active_pack", packId)
        }
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_SETTINGS_UPDATE
            putExtra(ResonaService.EXTRA_SETTINGS_JSON, settings.toString())
        }
        startService(intent)
    }

    private fun startResonaService(url: String) {
        pendingServiceUrl = url
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_START
            putExtra(ResonaService.EXTRA_BASE_URL, url)
        }
        appendConnectLog("启动 Service：$url")
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            bindServiceOnce()
        } catch (t: Throwable) {
            appendConnectLog("启动 Service 失败：${t.message ?: "unknown"}")
            reportClientError("启动 Service 失败：${t.message ?: "unknown"}")
        }
    }

    private fun isResonaServiceRunning(): Boolean {
        val manager = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager ?: return false
        @Suppress("DEPRECATION")
        val services = manager.getRunningServices(Int.MAX_VALUE)
        return services.any { it.service.className == ResonaService::class.java.name }
    }

    private fun bindServiceOnce() {
        if (serviceConnection != null) return
        val intent = Intent(this, ResonaService::class.java)
        val connection = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName, service: IBinder) {
                serviceBound = true
                lastServicePongAt = System.currentTimeMillis()
                appendConnectLog("Service 已绑定")
                val binder = service as? ResonaService.LocalBinder
                val url = pendingServiceUrl
                if (binder != null && !url.isNullOrBlank()) {
                    binder.startWithUrl(url)
                    appendConnectLog("通过 Binder 启动连接")
                }
            }

            override fun onServiceDisconnected(name: ComponentName) {
                serviceBound = false
                appendConnectLog("Service 已断开")
            }
        }
        serviceConnection = connection
        val ok = bindService(intent, connection, Context.BIND_AUTO_CREATE)
        appendConnectLog("绑定 Service：${if (ok) "请求成功" else "请求失败"}")
    }

    private fun requestPlayQueue() {
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_PLAY_QUEUE
        }
        startService(intent)
    }

    private fun lockInput() {
        textInput.isEnabled = false
        sendBtn.isEnabled = false
        micBtn.isEnabled = true
    }

    private fun lockAllInput() {
        textInput.isEnabled = false
        sendBtn.isEnabled = false
        micBtn.isEnabled = false
    }

    private fun unlockInput() {
        if (pendingResponse) return
        if (isRecording) return
        textInput.isEnabled = true
        sendBtn.isEnabled = true
        micBtn.isEnabled = true
    }

    private fun setDialogueEnabled(enabled: Boolean) {
        textInput.isEnabled = enabled
        sendBtn.isEnabled = enabled
        micBtn.isEnabled = enabled
        dialogueBox.alpha = if (enabled) 1f else 0.6f
    }

    private fun showDisplayText(text: String) {
        dialogueView.text = text
        dialogueView.visibility = View.VISIBLE
        textInput.visibility = View.GONE
    }

    private fun showInputBox(clearText: Boolean) {
        if (clearText) {
            textInput.setText("")
        }
        textInput.visibility = View.VISIBLE
        dialogueView.visibility = View.GONE
    }

    private fun markRequestSubmitted(displayText: String? = null) {
        pendingResponse = true
        setDialogueEnabled(false)
        val text = displayText ?: textInput.text.toString().trim()
        showDisplayText(text)
        textInput.setText("")
    }

    private fun finishPendingResponse() {
        if (!pendingResponse) return
        pendingResponse = false
        setDialogueEnabled(true)
        showInputBox(true)
    }

    private fun cancelPendingResponse() {
        if (!pendingResponse) return
        pendingResponse = false
        setDialogueEnabled(true)
        showInputBox(true)
    }

    private fun updateStatusDot(state: String) {
        val color = when (state) {
            "connected", "idle" -> 0xFF2ECC71.toInt()
            "disconnected" -> 0xFFE74C3C.toInt()
            "recording" -> 0xFFE74C3C.toInt()
            "thinking" -> 0xFFF1C40F.toInt()
            "busy", "listening", "connecting" -> 0xFFE67E22.toInt()
            else -> 0xFFCCCCCC.toInt()
        }
        val bg = statusDot.background
        if (bg != null) {
            bg.setTint(color)
        } else {
            statusDot.setBackgroundColor(color)
        }
    }

    private fun handleStatus(state: String, text: String?, imageUrl: String?) {
        currentState = state
        statusView.text = when (state) {
            "thinking" -> "思考中"
            "listening" -> "聆听中"
            "busy" -> "处理中"
            "connecting" -> "连接中"
            else -> "已连接"
        }
        when (state) {
            "thinking" -> {
                if (pendingResponse) lockAllInput() else lockInput()
                updateStatusDot("thinking")
                if (!text.isNullOrBlank()) {
                    if (pendingResponse) showDisplayText(text) else textInput.setText(text)
                }
                if (!imageUrl.isNullOrBlank()) loadImage(imageUrl)
            }
            "listening" -> {
                if (pendingResponse) lockAllInput() else lockInput()
                updateStatusDot("listening")
                if (!text.isNullOrBlank()) {
                    if (pendingResponse) showDisplayText(text) else textInput.setText(text)
                }
                if (!imageUrl.isNullOrBlank()) loadImage(imageUrl)
            }
            "busy" -> {
                if (pendingResponse) lockAllInput() else lockInput()
                updateStatusDot("busy")
            }
            "connecting" -> {
                if (pendingResponse) lockAllInput() else lockInput()
                updateStatusDot("connecting")
            }
            else -> {
                updateStatusDot("connected")
                if (!imageUrl.isNullOrBlank()) {
                    val now = System.currentTimeMillis()
                    if (lastOutfitChangeAt == 0L || now - lastOutfitChangeAt >= 1500L) {
                        lastIdleImageUrl = imageUrl
                        if (!isSpeaking) loadImage(imageUrl)
                    }
                }
                if (!isSpeaking && pendingResponse) {
                    finishPendingResponse()
                } else if (!isSpeaking) {
                    unlockInput()
                }
            }
        }
    }

    private fun onConnectionReady() {
        statusView.text = "已连接"
        updateStatusDot("connected")
        if (!isSpeaking && !pendingResponse) unlockInput()
        hideConnectLog()
    }

    private fun startRecording() {
        if (!ensureRecordPermission()) return
        val cfg = currentConfig
        val maxDuration = cfg?.sttMaxDuration ?: 6.5
        val silence = cfg?.sttSilenceThreshold ?: 1.0
        val file = File(cacheDir, "recording_${System.currentTimeMillis()}.wav")
        recorder = AudioRecorder(
            sampleRate = 16000,
            maxDurationSec = maxDuration,
            silenceSec = silence,
            onComplete = { output ->
                isRecording = false
                runOnUiThread {
                    updateStatusDot("busy")
                    markRequestSubmitted("Processing...")
                    uploadAudio(output)
                }
            },
            onError = { message ->
                isRecording = false
                runOnUiThread {
                    cancelPendingResponse()
                    unlockInput()
                    showInputBox(false)
                    textInput.setText("Error: $message")
                }
            }
        )
        isRecording = true
        lockInput()
        updateStatusDot("recording")
        textInput.setText("Listening...")
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_START_RECORDING
        }
        startService(intent)
        recorder?.start(file)
    }

    private fun stopRecording() {
        recorder?.stop()
        isRecording = false
    }

    private fun uploadAudio(file: File) {
        val sessionId = ResonaPrefs.getSessionId(this)
        val baseUrl = ResonaPrefs.getBaseUrl(this)
        if (sessionId.isBlank() || baseUrl.isBlank()) {
            cancelPendingResponse()
            unlockInput()
            showInputBox(false)
            textInput.setText("未连接")
            return
        }
        Thread {
            try {
                val reqBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("session_id", sessionId)
                    .addFormDataPart(
                        "file",
                        file.name,
                        RequestBody.create("audio/wav".toMediaTypeOrNull(), file)
                    )
                    .build()
                val req = Request.Builder()
                    .url(baseUrl.trimEnd('/') + "/upload_audio")
                    .post(reqBody)
                    .build()
                httpClient.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) {
                        runOnUiThread {
                            cancelPendingResponse()
                            unlockInput()
                            showInputBox(false)
                            textInput.setText("上传失败")
                        }
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    cancelPendingResponse()
                    unlockInput()
                    showInputBox(false)
                    textInput.setText("上传失败")
                }
            } finally {
                file.delete()
            }
        }.start()
    }

    private fun loadImage(url: String) {
        val token = imageLoadToken.incrementAndGet()
        Thread {
            try {
                val normalized = normalizeImageUrl(url)
                val req = Request.Builder().url(normalized).build()
                httpClient.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) return@use
                    val body = resp.body ?: return@use
                    val bytes = body.bytes()
                    val target = getTargetImageSize()
                    val options = BitmapFactory.Options().apply {
                        inJustDecodeBounds = true
                    }
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                    val sampleSize = calculateInSampleSize(
                        options.outWidth,
                        options.outHeight,
                        target.first,
                        target.second
                    )
                    val decodeOptions = BitmapFactory.Options().apply {
                        inSampleSize = sampleSize
                    }
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, decodeOptions) ?: return@use
                    runOnUiThread {
                        if (token != imageLoadToken.get()) return@runOnUiThread
                        try {
                            imageView.setBitmapWithCrop(bmp)
                        } catch (t: Throwable) {
                            imageView.setImageBitmap(bmp)
                            reportClientError("图片裁剪失败：${t.message ?: "unknown"}")
                        }
                    }
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    reportClientError("图片加载失败：${t.message ?: "unknown"}")
                }
            }
        }.start()
    }

    private fun normalizeImageUrl(url: String): String {
        val trimmed = url.trim()
        if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return trimmed
        val base = normalizeBaseUrl(ResonaPrefs.getBaseUrl(this))
        if (base.isBlank()) return trimmed
        val cleaned = if (trimmed.startsWith("/")) trimmed else "/$trimmed"
        return base.trimEnd('/') + cleaned
    }

    private fun getTargetImageSize(): Pair<Int, Int> {
        val w = imageView.width
        val h = imageView.height
        if (w > 0 && h > 0) return w to h
        val metrics = resources.displayMetrics
        return metrics.widthPixels to metrics.heightPixels
    }

    private fun calculateInSampleSize(width: Int, height: Int, reqWidth: Int, reqHeight: Int): Int {
        if (width <= 0 || height <= 0) return 1
        var inSampleSize = 1
        var halfWidth = width / 2
        var halfHeight = height / 2
        while (halfWidth / inSampleSize >= reqWidth && halfHeight / inSampleSize >= reqHeight) {
            inSampleSize *= 2
        }
        return inSampleSize.coerceAtLeast(1)
    }

    private fun showSettingsDialog() {
        val cfg = currentConfig
        val container = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(32, 24, 32, 16)
        }
        val packSpinner = Spinner(this)
        val outfitSpinner = Spinner(this)
        val packLabel = TextView(this).apply { text = "角色包" }
        val outfitLabel = TextView(this).apply { text = "服装" }
        val sttMaxLabel = TextView(this).apply { text = "录音最大时长（秒）" }
        val sttMaxInput = EditText(this).apply {
            setText(cfg?.sttMaxDuration?.toString() ?: "6.5")
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        }
        val sttSilenceLabel = TextView(this).apply { text = "静音停止阈值（秒）" }
        val sttSilenceInput = EditText(this).apply {
            setText(cfg?.sttSilenceThreshold?.toString() ?: "1.0")
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        }
        val descView = TextView(this)
        val authorView = TextView(this)
        val versionView = TextView(this)
        container.addView(packLabel)
        container.addView(packSpinner)
        container.addView(outfitLabel)
        container.addView(outfitSpinner)
        container.addView(sttMaxLabel)
        container.addView(sttMaxInput)
        container.addView(sttSilenceLabel)
        container.addView(sttSilenceInput)
        container.addView(descView)
        container.addView(authorView)
        container.addView(versionView)

        val packs = cfg?.availablePacks ?: emptyList()
        val packNames = packs.map { it.name }
        packSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, packNames)
        val selectedPackIndex = packs.indexOfFirst { it.id == cfg?.activePack }.coerceAtLeast(0)
        packSpinner.setSelection(selectedPackIndex)

        val outfitNames = outfits.map { it.name }
        outfitSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, outfitNames)

        val metadata = cfg?.packMetadata
        descView.text = "描述：${metadata?.description ?: "Unknown"}"
        authorView.text = "作者：${metadata?.author ?: "Unknown"}"
        versionView.text = "版本：${metadata?.version ?: "0.0.0"}"

        AlertDialog.Builder(this)
            .setTitle("设置")
            .setView(container)
            .setPositiveButton("确定") { _, _ ->
                val packIdx = packSpinner.selectedItemPosition
                val selectedPackId = if (packIdx >= 0 && packIdx < packs.size) packs[packIdx].id else ""
                val packChanged = selectedPackId.isNotBlank() && selectedPackId != cfg?.activePack
                if (packChanged) {
                    setActivePack(selectedPackId)
                    return@setPositiveButton
                }
                val outfitIdx = outfitSpinner.selectedItemPosition
                if (outfitIdx >= 0 && outfitIdx < outfits.size) {
                    setOutfit(outfits[outfitIdx].id)
                }
                val sttMax = sttMaxInput.text.toString().trim().toDoubleOrNull()
                val sttSilence = sttSilenceInput.text.toString().trim().toDoubleOrNull()
                val settings = JSONObject()
                if (sttMax != null) {
                    settings.put("stt_max_duration", sttMax)
                }
                if (sttSilence != null) {
                    settings.put("stt_silence_threshold", sttSilence)
                }
                if (settings.length() > 0) {
                    val intent = Intent(this, ResonaService::class.java).apply {
                        action = ResonaService.ACTION_SETTINGS_UPDATE
                        putExtra(ResonaService.EXTRA_SETTINGS_JSON, settings.toString())
                    }
                    startService(intent)
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun parseConfig(json: String): WebConfig {
        val obj = JSONObject(json)
        val available = mutableListOf<PackInfo>()
        val list = obj.optJSONArray("available_packs")
        if (list != null) {
            for (i in 0 until list.length()) {
                val p = list.optJSONObject(i) ?: continue
                available.add(
                    PackInfo(
                        id = p.optString("id"),
                        name = p.optString("name", p.optString("id")),
                        description = p.optString("description", "")
                    )
                )
            }
        }
        val metaObj = obj.optJSONObject("pack_metadata")
        val metadata = if (metaObj != null) {
            PackMetadata(
                name = metaObj.optString("name", "Unknown"),
                description = metaObj.optString("description", "No description"),
                author = metaObj.optString("author", "Unknown"),
                version = metaObj.optString("version", "0.0.0")
            )
        } else {
            null
        }
        return WebConfig(
            sttMaxDuration = obj.optDouble("stt_max_duration", 6.5),
            sttSilenceThreshold = obj.optDouble("stt_silence_threshold", 1.0),
            sovitsEnabled = obj.optBoolean("sovits_enabled", true),
            textReadSpeed = obj.optDouble("text_read_speed", 0.2),
            baseDisplayTime = obj.optDouble("base_display_time", 2.0),
            activePack = obj.optString("active_pack", ""),
            defaultOutfit = obj.optString("default_outfit", ""),
            characterName = obj.optString("character_name", "Resona"),
            initialImageUrl = obj.optString("initial_image_url", null),
            packMetadata = metadata,
            availablePacks = available
        )
    }

    private fun requestPermissionsIfNeeded() {
        val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val need = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (need.isNotEmpty()) {
            requestPermissions(need.toTypedArray(), 1001)
        }
    }

    private fun ensureRecordPermission(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    }

    private fun startDiscovery() {
        if (discovering.getAndSet(true)) return
        discoveryToken += 1
        val token = discoveryToken
        discoveryFound = false
        if (!isWifiConnected()) {
            runOnUiThread {
                statusView.text = "请使用 Wi-Fi 或手动输入地址"
                updateStatusDot("disconnected")
                appendConnectLog("当前非 Wi-Fi，跳过发现")
            }
            textInput.postDelayed({
                if (token != discoveryToken) return@postDelayed
                showManualConnectDialog("当前非 Wi-Fi，请手动输入地址")
            }, 2000)
            discovering.set(false)
            return
        }
        appendConnectLog("开始发现局域网服务器")
        textInput.postDelayed({
            if (token != discoveryToken) return@postDelayed
            if (!discoveryFound) {
                showManualConnectDialog("2 秒内未发现服务器，请手动输入地址")
            }
        }, 2000)
        discoveryThread = Thread {
            val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            if (wifi == null) {
                runOnUiThread {
                    statusView.text = "未发现 Wi-Fi"
                    updateStatusDot("disconnected")
                    appendConnectLog("未发现 Wi-Fi")
                }
                discovering.set(false)
                return@Thread
            }
            val lock = wifi.createMulticastLock("resona_discovery")
            lock.setReferenceCounted(false)
            lock.acquire()
            try {
                DatagramSocket(50123, InetAddress.getByName("0.0.0.0")).use { socket ->
                    socket.soTimeout = 500
                    socket.broadcast = true
                    val ping = JSONObject()
                    ping.put("type", "resona_discovery")
                    val payload = ping.toString().toByteArray(Charsets.UTF_8)
                    socket.send(DatagramPacket(payload, payload.size, InetAddress.getByName("255.255.255.255"), 50123))
                    val buf = ByteArray(2048)
                    var found = false
                    val deadline = System.currentTimeMillis() + 2000
                    while (discovering.get() && System.currentTimeMillis() < deadline) {
                        val packet = DatagramPacket(buf, buf.size)
                        try {
                            socket.receive(packet)
                        } catch (e: SocketTimeoutException) {
                            continue
                        }
                        val message = String(packet.data, 0, packet.length, Charsets.UTF_8)
                        val json = JSONObject(message)
                        if (json.optString("type") == "resona_server") {
                            val port = json.optInt("port", 8000)
                            val ip = packet.address.hostAddress
                            val url = "http://$ip:$port"
                            runOnUiThread {
                                ResonaPrefs.saveBaseUrl(this, url)
                                startConnection(url, "发现服务器")
                            }
                            found = true
                            discoveryFound = true
                            discovering.set(false)
                        }
                    }
                    if (!found) {
                        discovering.set(false)
                    }
                }
            } catch (_: Exception) {
            } finally {
                lock.release()
            }
        }
        discoveryThread?.start()
    }

    private fun isWifiConnected(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }

    private fun showManualConnectDialog(reason: String) {
        runOnUiThread {
            hideConnectLog()
            val savedUrl = normalizeBaseUrl(ResonaPrefs.getBaseUrl(this))
            val input = EditText(this).apply {
                setText(savedUrl)
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                setSelection(text?.length ?: 0)
            }
            AlertDialog.Builder(this)
                .setTitle("手动连接")
                .setMessage(reason)
                .setView(input)
                .setPositiveButton("连接") { _, _ ->
                    val url = normalizeBaseUrl(input.text.toString().trim())
                    if (url.isNotBlank()) {
                        ResonaPrefs.saveBaseUrl(this, url)
                        startConnection(url, "手动连接")
                    } else {
                        statusView.text = "请输入服务器地址"
                    }
                }
                .setNegativeButton("取消", null)
                .show()
        }
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

    private fun startConnection(url: String, source: String) {
        gotConfig = false
        gotOutfits = false
        appendConnectLog("$source：$url")
        showConnectLog()
        startResonaService(url)
        sendServicePing()
        textInput.postDelayed({
            val delta = System.currentTimeMillis() - lastServicePongAt
            if (lastServicePongAt == 0L || delta > 1500) {
                appendConnectLog("Service 无响应")
            }
        }, 1500)
        statusView.text = "连接中：$url"
        updateStatusDot("busy")
        probeServer(url)
    }

    private fun registerEventReceiverIfNeeded() {
        if (receiverRegistered) return
        appendConnectLog("接收器注册")
        val filter = IntentFilter().apply {
            addAction(ResonaService.ACTION_EVENT)
            addAction(ResonaService.ACTION_STATUS)
            addAction(ResonaService.ACTION_TRANSCRIPTION)
            addAction(ResonaService.ACTION_ERROR)
            addAction(ResonaService.ACTION_OUTFITS)
            addAction(ResonaService.ACTION_OUTFIT_CHANGED)
            addAction(ResonaService.ACTION_CONFIG)
            addAction(ResonaService.ACTION_PLAYBACK_STARTED)
            addAction(ResonaService.ACTION_PLAYBACK_FINISHED)
        }
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                registerReceiver(eventReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                @Suppress("DEPRECATION")
                registerReceiver(eventReceiver, filter)
            }
            receiverRegistered = true
        } catch (t: Exception) {
            appendConnectLog("接收器注册失败：${t.message ?: "unknown"}")
        }
    }

    private fun sendServicePing() {
        val intent = Intent(this, ResonaService::class.java).apply {
            action = ResonaService.ACTION_PING
        }
        startService(intent)
    }

    private fun unregisterEventReceiverIfNeeded() {
        if (!receiverRegistered) return
        try {
            unregisterReceiver(eventReceiver)
        } catch (_: Exception) {
        } finally {
            receiverRegistered = false
        }
    }

    private fun showConnectLog() {
        if (!connectLogEnabled) return
        if (connectLogVisible) return
        connectLogOverlay.visibility = View.VISIBLE
        connectLogVisible = true
    }

    private fun hideConnectLog() {
        connectLogOverlay.visibility = View.GONE
        connectLogVisible = false
    }

    private fun appendConnectLog(message: String) {
        if (!connectLogEnabled) return
        runOnUiThread {
            showConnectLog()
            if (connectLogBuffer.isNotEmpty()) {
                connectLogBuffer.append("\n")
            }
            connectLogBuffer.append(message)
            if (connectLogBuffer.length > 8000) {
                connectLogBuffer.delete(0, connectLogBuffer.length - 8000)
            }
            connectLogText.text = connectLogBuffer.toString()
        }
    }

    private fun probeServer(baseUrl: String) {
        val url = baseUrl.trimEnd('/') + "/__static_info"
        appendConnectLog("探测：$url")
        Thread {
            try {
                val req = Request.Builder().url(url).build()
                probeClient.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) {
                        runOnUiThread {
                            reportClientError("连接失败：HTTP ${resp.code}")
                        }
                    } else {
                        appendConnectLog("探测成功：HTTP ${resp.code}")
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    reportClientError("连接失败：${e.message ?: "unknown"}")
                }
            }
        }.start()
    }

    private fun reportClientError(message: String) {
        appendConnectLog("错误：$message")
        showErrorPopup(message)
        statusView.text = "连接失败"
        updateStatusDot("disconnected")
        cancelPendingResponse()
        unlockInput()
    }

    private fun showErrorPopup(message: String) {
        runOnUiThread {
            try {
                val dialog = AlertDialog.Builder(this)
                    .setMessage(message)
                    .setCancelable(true)
                    .create()
                dialog.setCanceledOnTouchOutside(true)
                dialog.show()
            } catch (_: Throwable) {
            }
        }
    }
}
