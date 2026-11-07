package ru.liftcontrol.liftcontrol_mobile

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import org.json.JSONObject

class LiftApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        PushState.initialize(this)
    }
}

object PushState {
    const val CHANNEL = "liftcontrol_requests_v1"
    fun prefs(context: Context) = context.getSharedPreferences("push_settings", Context.MODE_PRIVATE)
    fun initialize(context: Context): FirebaseApp? {
        if (FirebaseApp.getApps(context).isNotEmpty()) return FirebaseApp.getInstance()
        val raw = prefs(context).getString("config", null) ?: return null
        return try {
            val data = JSONObject(raw)
            FirebaseApp.initializeApp(context, FirebaseOptions.Builder()
                .setApiKey(data.getString("apiKey")).setApplicationId(data.getString("appId"))
                .setProjectId(data.getString("projectId")).setGcmSenderId(data.getString("messagingSenderId"))
                .build())
        } catch (_: Exception) { null }
    }
    fun channel(context: Context) {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = context.getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(CHANNEL, "Заявки и остановки лифтов", NotificationManager.IMPORTANCE_HIGH)
            channel.description = "Новые заявки, работа и остановки лифтов"
            channel.enableVibration(true)
            channel.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build())
            manager.createNotificationChannel(channel)
        }
    }
    fun show(context: Context, organization: Int, ticket: Int, title: String, body: String) {
        channel(context)
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return
        val tag = "o$organization-t$ticket"
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("organization", organization); putExtra("ticket", ticket)
        }
        val pending = PendingIntent.getActivity(context, tag.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(title).setContentText(body)
            .setContentIntent(pending).setAutoCancel(true).setOnlyAlertOnce(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setDefaults(NotificationCompat.DEFAULT_ALL).build()
        try { NotificationManagerCompat.from(context).notify(tag, 1, notification) } catch (_: SecurityException) { }
    }
}

class LiftMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        // Token is registered with our authenticated API on the next foreground sync.
        PushState.prefs(this).edit().putBoolean("needs_register", true).apply()
        DeviceBridge.tokenChanged()
    }
    override fun onMessageReceived(message: RemoteMessage) {
        val prefs = PushState.prefs(this)
        if (!prefs.getBoolean("active", false)) return
        val data = message.data
        val organization = data["organization_id"]?.toIntOrNull() ?: return
        val ticket = data["ticket_id"]?.toIntOrNull() ?: return
        val event = data["event_id"]?.toLongOrNull() ?: return
        if (organization <= 0 || ticket <= 0 || event <= 0) return
        if (message.sentTime > 0 && System.currentTimeMillis() - message.sentTime > 5 * 60 * 1000L) return
        val key = "cursor-o$organization-t$ticket"
        synchronized(PushState) {
            if (event <= prefs.getLong(key, 0)) return
            prefs.edit().putLong(key, event).apply()
        }
        val title = when (data["kind"]) {
            "created" -> "Новая заявка"
            "accepted" -> "Заявка принята в работу"
            "completed" -> "Заявка выполнена"
            "canceled" -> "Заявка отменена"
            "stopped" -> "Лифт остановлен"
            "resumed" -> "Ремонт продолжен"
            "reassigned" -> "Изменён исполнитель"
            else -> return
        }
        PushState.show(this, organization, ticket, "$title #$ticket", "Откройте заявку для просмотра подробностей")
    }
}
