package ru.liftcontrol.liftcontrol_mobile

import android.content.Context
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import org.json.JSONObject

// A bounded capability fetch: never sends a bearer token, never follows redirects.
fun fetchPushContent(context: Context, data: Map<String, String>): String? {
    val token = data["content_token"] ?: return null
    if (token.length !in 1..500) return null
    val server = PushState.prefs(context).getString("receipt_server", null) ?: return null
    return try {
        val base = URL(server)
        require(base.protocol == "https" && base.userInfo == null && base.query == null &&
            base.ref == null && base.host.isNotBlank() && base.path in listOf("", "/"))
        val connection = URL(base, "/api/mobile/push/content/").openConnection() as HttpsURLConnection
        try {
            connection.requestMethod = "POST"
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 3000
            connection.readTimeout = 3000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            val payload = JSONObject().put("token", token).toString().toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(payload.size)
            connection.outputStream.use { it.write(payload) }
            if (connection.responseCode != 200) null else {
                val bytes = connection.inputStream.use { input ->
                    val output = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(4096)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        require(output.size() + count <= 65536)
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                }
                require(bytes.size <= 65536)
                JSONObject(String(bytes, Charsets.UTF_8)).getString("body")
            }
        } finally { connection.disconnect() }
    } catch (_: Exception) {
        PushState.record(context, "notification_content_failed")
        null
    }
}
