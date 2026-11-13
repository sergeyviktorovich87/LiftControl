package ru.liftcontrol.liftcontrol_mobile

import android.content.Context

/**
 * Shared FCM/self-hosted event renderer. Identical event IDs are notified once
 * even when both transports deliver the same business change.
 *
 * Payloads are intentionally metadata-only, no employee names, addresses,
 * ticket descriptions, API bearer tokens, or confidential repair data.
 */
fun displayPushEvent(context: Context, data: Map<String, String>, source: String): Boolean {
    val organization = data["organization_id"]?.toIntOrNull() ?: return false
    val personal = data["target"] == "task"
    val target = if (personal) "task" else "ticket"
    val objectId = data[if (personal) "task_id" else "ticket_id"]?.toIntOrNull() ?: return false
    val eventId = data["event_id"]?.toLongOrNull() ?: return false
    if (organization <= 0 || objectId <= 0 || eventId <= 0) return false

    val kind = data["kind"] ?: return false
    val title = if (personal) when (kind) {
        "created", "assigned" -> "Новое личное задание"
        "accepted" -> "Личное задание принято"
        "completed" -> "Личное задание выполнено"
        "canceled" -> "Личное задание отменено"
        else -> return false
    } else when (kind) {
        "created" -> "Новая заявка"
        "accepted" -> "Заявка принята в работу"
        "completed" -> "Заявка выполнена"
        "canceled" -> "Заявка отменена"
        "stopped" -> "Лифт остановлен"
        "resumed" -> "Ремонт продолжен"
        "reassigned" -> "Изменён исполнитель"
        else -> return false
    }

    val initial = kind in listOf("created", "reassigned")
    val group = if (personal) "tasks" else if (!initial) "updates" else when (data["priority"]) {
        "ENTRAPMENT" -> "entrapment"
        "HIGH", "EMERGENCY" -> "urgent"
        else -> "ordinary"
    }
    val prefs = PushState.prefs(context)
    val key = "cursor-o$organization-$target-$objectId"
    synchronized(PushState) {
        if (eventId <= prefs.getLong(key, 0)) {
            PushState.record(context, "${source}_duplicate_suppressed")
            return false
        }
        prefs.edit().putLong(key, eventId).apply()
    }

    val headline = if (group == "entrapment") "Застревание: люди в кабине" else title
    PushState.show(context, organization, objectId, "$headline #$objectId",
        "Откройте для просмотра подробностей", group, target)
    PushState.record(context, "${source}_event_displayed")
    return true
}
