package ru.liftcontrol.liftcontrol_mobile

import android.content.Context
import android.os.Build

/**
 * Shared FCM/self-hosted event renderer. Identical event IDs are notified once
 * even when both transports deliver the same business change.
 *
 * Full content is fetched from the protected server. FCM only carries event
 * metadata and a short-lived capability, never the API bearer token.
 */
fun displayPushEvent(context: Context, data: Map<String, String>, source: String): Boolean {
    if (data["target"] == "app_update") {
        val versionCode = data["version_code"]?.toLongOrNull() ?: return false
        if (versionCode <= 0 || versionCode > 2100000000) return false
        val current = try {
            @Suppress("DEPRECATION")
            val info = context.packageManager.getPackageInfo(context.packageName, 0)
            if (Build.VERSION.SDK_INT >= 28) info.longVersionCode
            else @Suppress("DEPRECATION") info.versionCode.toLong()
        } catch (_: Exception) {
            PushState.record(context, "app_update_version_unavailable")
            return false
        }
        if (versionCode <= current) {
            PushState.record(context, "app_update_already_installed")
            return false
        }
        val prefs = PushState.prefs(context)
        synchronized(PushState) {
            if (versionCode <= prefs.getLong("app_update_last_notified", 0L)) {
                PushState.record(context, "app_update_duplicate_suppressed")
                return false
            }
            prefs.edit().putLong("app_update_last_notified", versionCode).apply()
        }
        val name = data["version"]?.takeIf {
            it.matches(Regex("^[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}$"))
        } ?: versionCode.toString()
        val shown = PushState.show(
            context, 0, versionCode.toInt(),
            "Обновление Лифт Контроль",
            "Доступна версия $name. Откройте приложение, чтобы обновиться.",
            "app_update", "app_update"
        )
        if (shown) PushState.record(context, "${source}_app_update_displayed")
        return shown
    }
    val organization = data["organization_id"]?.toIntOrNull() ?: return false
    val target = when (data["target"]) {
        "ticket_comment" -> "ticket_comment"
        "chat" -> "chat"
        "task" -> "task"
        "ticket_delivery" -> "ticket_delivery"
        "commissioning" -> "commissioning"
        "commissioning_chat" -> "commissioning_chat"
        "inspection" -> "inspection"
        else -> "ticket"
    }
    val personal = target == "task"
    val commissioning = target == "commissioning"
    val teamChat = target == "commissioning_chat" || target == "chat"
    val inspection = target == "inspection"
    val objectId = data[when (target) {
        "task" -> "task_id"
        "commissioning" -> "project_id"
        "chat", "commissioning_chat" -> "message_id"
        "inspection" -> "elevator_id"
        else -> "ticket_id"
    }]?.toIntOrNull() ?: return false
    val eventId = data["event_id"]?.toLongOrNull() ?: return false
    if (organization <= 0 || objectId <= 0 || eventId <= 0) return false

    val kind = data["kind"] ?: return false
    val title = if (inspection) {
        if (kind != "reminder") return false
        "Предстоит освидетельствование лифта"
    } else if (teamChat) {
        if (kind != "message") return false
        if (target == "chat") "Новое сообщение в чате команды" else "Новое сообщение в чате наладчиков"
    } else if (commissioning) when (kind) {
        "progress" -> "Комментарий по пусконаладке"
        "expense_created" -> "Новый расход на наладку"
        "expense_reimbursed" -> "Расход на наладку возмещён"
        "lift_assigned" -> "Назначен лифт на наладку"
        "lift_requested" -> "Запрошен лифт для наладки"
        "lift_decided" -> "Рассмотрено добавление лифта"
        "need_created" -> "Новая потребность по наладке"
        "need_resolved" -> "Потребность по наладке закрыта"
        "extra_proposed" -> "Предложены дополнительные работы"
        "extra_decided" -> "Рассмотрены дополнительные работы"
        else -> return false
    } else if (target == "ticket_delivery") {
        if (kind != "unconfirmed") return false
        "Нет подтверждения доставки заявки"
    } else if (personal) when (kind) {
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
        "long_repair" -> "Длительный ремонт"
        "reassigned" -> "Изменён исполнитель"
        "comment" -> "Комментарий к заявке"
        else -> return false
    }

    val initial = kind in listOf("created", "reassigned")
    val group = when {
        inspection -> "inspection"
        teamChat -> if (target == "chat") "updates" else "commissioning_chat"
        commissioning -> "commissioning"
        personal -> "tasks"
        !initial -> "updates"
        data["priority"] == "ENTRAPMENT" -> "entrapment"
        data["priority"] in listOf("HIGH", "EMERGENCY") -> "urgent"
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
    val shown = PushState.show(context, organization, objectId, if (commissioning || teamChat || inspection) headline else "$headline #$objectId",
        data["body"]?.takeIf { it.isNotBlank() } ?: "Откройте для просмотра подробностей", group, target, eventId)
    if (shown) PushState.record(context, "${source}_event_displayed")
    return shown
}
