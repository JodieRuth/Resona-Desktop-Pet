package com.resona.client

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

class ResonaWebSocket(
    private val client: OkHttpClient,
    private val baseUrl: String,
    private val sessionId: String,
    private val onConnecting: (String) -> Unit,
    private val onOpen: (String) -> Unit,
    private val onSpeak: (SpeakEvent) -> Unit,
    private val onHandshake: (String, WebConfig) -> Unit,
    private val onStatus: (StatusMessage) -> Unit,
    private val onTranscription: (String) -> Unit,
    private val onError: (String) -> Unit,
    private val onOutfits: (OutfitListMessage) -> Unit,
    private val onOutfitChanged: (OutfitChangedMessage) -> Unit,
    private val onTimerEvent: (TimerEventMessage) -> Unit,
    private val onConfigUpdated: (WebConfig) -> Unit
) {
    private var socket: WebSocket? = null

    fun connect() {
        val wsUrl = try {
            toWebSocketUrl(baseUrl)
        } catch (e: Exception) {
            onError("WebSocket 地址无效：${e.message ?: "unknown"}")
            return
        }
        onConnecting(wsUrl)
        val request = try {
            Request.Builder().url(wsUrl).build()
        } catch (e: Exception) {
            onError("WebSocket 地址无效：${e.message ?: "unknown"}")
            return
        }
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                onOpen(wsUrl)
                val handshake = JSONObject()
                handshake.put("type", "handshake")
                handshake.put("session_id", sessionId)
                handshake.put("pack_id", "default")
                webSocket.send(handshake.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val msg = JSONObject(text)
                    val type = msg.optString("type")
                    if (type == "speak") {
                        val textDisplay = msg.optString("text", msg.optString("text_display", ""))
                        val audioUrl = msg.optString("audio_url", null)
                        val imageUrl = msg.optString("image_url", null)
                        onSpeak(
                            SpeakEvent(
                                text = textDisplay,
                                audioUrl = normalizeUrl(baseUrl, audioUrl),
                                imageUrl = normalizeUrl(baseUrl, imageUrl)
                            )
                        )
                    } else if (type == "handshake_ack") {
                        val newSessionId = msg.optString("session_id", sessionId)
                        val config = parseWebConfig(msg.optJSONObject("config"))
                        onHandshake(newSessionId, config)
                    } else if (type == "status") {
                        val state = msg.optString("state")
                        val textValue = msg.optString("text", null)
                        val imageUrl = msg.optString("image_url", null)
                        onStatus(
                            StatusMessage(
                                state = state,
                                text = if (textValue.isNullOrBlank()) null else textValue,
                                imageUrl = normalizeUrl(baseUrl, imageUrl)
                            )
                        )
                    } else if (type == "transcription") {
                        onTranscription(msg.optString("text"))
                    } else if (type == "error") {
                        onError(msg.optString("message", "unknown error"))
                    } else if (type == "outfits_list") {
                        val outfits = mutableListOf<OutfitInfo>()
                        val list = msg.optJSONArray("outfits")
                        if (list != null) {
                            for (i in 0 until list.length()) {
                                val o = list.optJSONObject(i) ?: continue
                                outfits.add(
                                    OutfitInfo(
                                        id = o.optString("id"),
                                        name = o.optString("name", o.optString("id")),
                                        isDefault = o.optBoolean("is_default", false)
                                    )
                                )
                            }
                        }
                        onOutfits(
                            OutfitListMessage(
                                packId = msg.optString("pack_id"),
                                outfits = outfits,
                                currentOutfit = msg.optString("current_outfit")
                            )
                        )
                    } else if (type == "outfit_changed") {
                        onOutfitChanged(
                            OutfitChangedMessage(
                                outfitId = msg.optString("outfit_id"),
                                imageUrl = normalizeUrl(baseUrl, msg.optString("image_url", null))
                            )
                        )
                    } else if (type == "timer_event") {
                        val task = msg.optJSONObject("task")
                        val textDisplay = task?.optString("text_display", "") ?: ""
                        val textTts = task?.optString("text_tts", "") ?: ""
                        val textValue = if (textDisplay.isNotBlank()) textDisplay else textTts
                        val audioUrl = normalizeUrl(baseUrl, task?.optString("audio_url", null))
                        val imageUrl = normalizeUrl(baseUrl, task?.optString("image_url", null))
                        val duration = task?.optDouble("duration", 0.0) ?: 0.0
                        val triggerAt = msg.optDouble("trigger_at", task?.optDouble("due_at", Double.NaN) ?: Double.NaN)
                        onTimerEvent(
                            TimerEventMessage(
                                text = textValue,
                                audioUrl = audioUrl,
                                imageUrl = imageUrl,
                                duration = duration,
                                triggerAt = if (triggerAt.isNaN()) null else triggerAt
                            )
                        )
                    } else if (type == "config_updated") {
                        val config = parseWebConfig(msg.optJSONObject("config"))
                        onConfigUpdated(config)
                    }
                } catch (t: Throwable) {
                    onError("WebSocket 消息解析失败：${t.message ?: "unknown"}")
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val message = t.message ?: "unknown failure"
                val code = response?.code
                val extra = if (code != null) " HTTP $code" else ""
                onError("WebSocket 连接失败：${t::class.java.simpleName} $message$extra")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (code != 1000) {
                    val message = if (reason.isBlank()) "code=$code" else reason
                    onError("WebSocket 连接关闭：$message")
                }
            }
        })
    }

    fun close() {
        socket?.close(1000, "closed")
    }

    fun sendJson(payload: JSONObject): Boolean {
        return socket?.send(payload.toString()) ?: false
    }

    private fun toWebSocketUrl(httpUrl: String): String {
        val normalized = httpUrl.trim().trimEnd('/')
        return if (normalized.startsWith("https://")) {
            normalized.replaceFirst("https://", "wss://") + "/ws"
        } else {
            normalized.replaceFirst("http://", "ws://") + "/ws"
        }
    }

    private fun normalizeUrl(base: String, path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http://") || path.startsWith("https://")) return path
        val normalized = base.trim().trimEnd('/')
        val cleaned = if (path.startsWith("/")) path else "/$path"
        return normalized + cleaned
    }

    private fun parseWebConfig(obj: JSONObject?): WebConfig {
        val config = obj ?: JSONObject()
        val available = mutableListOf<PackInfo>()
        val packs = config.optJSONArray("available_packs")
        if (packs != null) {
            for (i in 0 until packs.length()) {
                val p = packs.optJSONObject(i) ?: continue
                available.add(
                    PackInfo(
                        id = p.optString("id"),
                        name = p.optString("name", p.optString("id")),
                        description = p.optString("description", "")
                    )
                )
            }
        }
        val metadataObj = config.optJSONObject("pack_metadata")
        val metadata = if (metadataObj != null) {
            PackMetadata(
                name = metadataObj.optString("name", "Unknown"),
                description = metadataObj.optString("description", "No description"),
                author = metadataObj.optString("author", "Unknown"),
                version = metadataObj.optString("version", "0.0.0")
            )
        } else {
            null
        }
        return WebConfig(
            sttMaxDuration = config.optDouble("stt_max_duration", 6.5),
            sttSilenceThreshold = config.optDouble("stt_silence_threshold", 1.0),
            sovitsEnabled = config.optBoolean("sovits_enabled", true),
            textReadSpeed = config.optDouble("text_read_speed", 0.2),
            baseDisplayTime = config.optDouble("base_display_time", 2.0),
            activePack = config.optString("active_pack", ""),
            defaultOutfit = config.optString("default_outfit", ""),
            characterName = if (config.has("character_name")) config.optString("character_name", "") else "",
            initialImageUrl = normalizeUrl(baseUrl, config.optString("initial_image_url", null)),
            packMetadata = metadata,
            availablePacks = available
        )
    }
}
