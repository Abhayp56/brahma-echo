package com.brahma.connect.core

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

enum class ConnectionState {
    CONNECTING,
    CONNECTED,
    DISCONNECTED,
    RECONNECTING,
}

data class GatewayEndpoint(
    val name: String,
    val host: String,
    val port: Int,
    val online: Boolean = true,
    val ssl: Boolean = false,
    val path: String = "/ws",
    val url: String = "",
)

data class PairingOffer(
    val service: String,
    val host: String,
    val port: Int,
    val pairingToken: String,
    val pairingCode: String,
    val expiresInSeconds: Int,
    val createdAt: String,
    val ssl: Boolean = false,
    val path: String = "/ws",
    val url: String = "",
) {
    companion object {
        fun fromJson(json: JSONObject): PairingOffer {
            val url = json.optString("url")
            val isSsl = json.optBoolean("ssl", false) || url.startsWith("wss://")
            val path = json.optString("path", if (url.contains("/ws/phone")) "/ws/phone" else "/ws")
            val host = json.optString("host")
            val defaultPort = if (isSsl) 443 else 8765
            val port = json.optInt("port", defaultPort).let { if (it <= 0) defaultPort else it }
            return PairingOffer(
                service = json.optString("service", "Brahma"),
                host = host,
                port = port,
                pairingToken = json.optString("pairing_token"),
                pairingCode = json.optString("pairing_code"),
                expiresInSeconds = json.optInt("expires", 600),
                createdAt = json.optString("created_at"),
                ssl = isSsl,
                path = path,
                url = url,
            )
        }
    }

    fun toJson(): JSONObject = JSONObject()
        .put("service", service)
        .put("host", host)
        .put("port", port)
        .put("pairing_token", pairingToken)
        .put("pairing_code", pairingCode)
        .put("expires", expiresInSeconds)
        .put("created_at", createdAt)
        .put("ssl", ssl)
        .put("path", path)
        .put("url", url)
}

data class DeviceCredential(
    val deviceId: String,
    val deviceSecret: String,
    val deviceName: String,
    val gatewayHost: String,
    val gatewayPort: Int,
    val pairedAt: String = Instant.now().toString(),
    val gatewayUrl: String = "",
    val ssl: Boolean = false,
)

data class DeviceSnapshot(
    val deviceId: String?,
    val deviceName: String,
    val platform: String = "android",
    val androidVersion: String,
    val agentVersion: String,
    val batteryPercentage: Int,
    val charging: Boolean,
    val wifiEnabled: Boolean,
    val capabilities: List<String>,
    val permissions: List<String> = emptyList(),
    val metadata: Map<String, Any?> = emptyMap(),
) {
    fun toJson(): JSONObject = JSONObject()
        .put("device_id", deviceId ?: JSONObject.NULL)
        .put("device_name", deviceName)
        .put("platform", platform)
        .put("os_version", androidVersion)
        .put("agent_version", agentVersion)
        .put("battery", batteryPercentage)
        .put("charging", charging)
        .put("wifi_state", if (wifiEnabled) "connected" else "disconnected")
        .put("capabilities", JSONArray(capabilities))
        .put("permissions", JSONArray(permissions))
        .put("metadata", JSONObject(metadata))
}

data class ChatMessage(
    val id: String,
    val role: String,
    val text: String,
    val timestamp: Long,
    val status: String
)

enum class CallState {
    IDLE,
    RINGING,
    ACTIVE,
    ENDED,
}

data class CallOfferPayload(
    val callId: String,
    val callerName: String = "ARYA",
    val reason: String = "Voice Call",
    val timestamp: Long = System.currentTimeMillis(),
)

data class CommandResult(
    val success: Boolean,
    val data: Map<String, Any?> = emptyMap(),
    val errorCode: String? = null,
    val error: String? = null,
) {
    fun toJson(): JSONObject {
        val json = JSONObject()
            .put("success", success)
        if (data.isNotEmpty()) {
            json.put("data", toJsonValue(data))
        }
        if (!errorCode.isNullOrBlank()) {
            json.put("error_code", errorCode)
        }
        if (!error.isNullOrBlank()) {
            json.put("error", error)
        }
        return json
    }
}

object BrahmaProtocol {
    const val HELLO = "hello"
    const val PAIR_REQUEST = "pair_request"
    const val PAIR_APPROVED = "pair_approved"
    const val AUTHENTICATE = "authenticate"
    const val DEVICE_ONLINE = "device_online"
    const val DEVICE_OFFLINE = "device_offline"
    const val CAPABILITIES = "capabilities"
    const val EXECUTE = "execute"
    const val RESULT = "result"
    const val EVENT = "event"
    const val ERROR = "error"
    const val PING = "ping"
    const val PONG = "pong"
    const val CHAT_MESSAGE = "chat_message"

    // Voice Calling Protocol
    const val CALL_OFFER = "call_offer"
    const val CALL_ANSWER = "call_answer"
    const val CALL_REJECT = "call_reject"
    const val CALL_END = "call_end"
    const val CALL_AUDIO = "call_audio"

    fun envelope(type: String, payload: JSONObject = JSONObject(), requestId: String = UUID.randomUUID().toString().replace("-", "")): JSONObject {
        return JSONObject()
            .put("type", type)
            .put("request_id", requestId)
            .put("timestamp", Instant.now().toString())
            .put("payload", payload)
    }

    fun hello(snapshot: DeviceSnapshot): JSONObject = envelope(
        HELLO,
        snapshot.toJson()
    )

    fun authenticate(credential: DeviceCredential): JSONObject = envelope(
        AUTHENTICATE,
        JSONObject()
            .put("device_id", credential.deviceId)
            .put("device_secret", credential.deviceSecret)
    )

    fun ping(): JSONObject = envelope(PING)

    fun chatMessage(text: String): JSONObject = envelope(
        CHAT_MESSAGE,
        JSONObject().put("text", text)
    )

    fun callAnswer(callId: String): JSONObject = envelope(
        CALL_ANSWER,
        JSONObject().put("call_id", callId)
    )

    fun callReject(callId: String, reason: String = "declined"): JSONObject = envelope(
        CALL_REJECT,
        JSONObject().put("call_id", callId).put("reason", reason)
    )

    fun callEnd(callId: String): JSONObject = envelope(
        CALL_END,
        JSONObject().put("call_id", callId)
    )

    fun callAudio(callId: String, dataBase64: String): JSONObject = envelope(
        CALL_AUDIO,
        JSONObject().put("call_id", callId).put("data", dataBase64)
    )
}

fun toJsonValue(value: Any?): Any? {
    return when (value) {
        null -> JSONObject.NULL
        is JSONObject -> value
        is JSONArray -> value
        is Map<*, *> -> JSONObject(value.entries.associate { (k, v) -> k.toString() to toJsonValue(v) })
        is Iterable<*> -> JSONArray(value.map { toJsonValue(it) })
        is Boolean, is Int, is Long, is Float, is Double, is String -> value
        else -> value.toString()
    }
}
