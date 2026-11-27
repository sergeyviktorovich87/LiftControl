from django.urls import include,path
from rest_framework.routers import DefaultRouter
from . import views, organizations, mobile_auth, native_push, updates, system_updates
from . import notification_preferences, mobile_sync, self_push, ticket_delivery, duty_analytics, roster, vacations, duty_planning, planning_push
from . import mechanics, webpush_health
from .work_orders import TaskViewSet
router = DefaultRouter()
router.register('tasks',TaskViewSet)
mobile_urls = [
    path('mobile/sync/', mobile_sync.synchronize),
    path('mobile/ticket-delivery/', ticket_delivery.acknowledge),
    path('mobile/ticket-delivery/push/', ticket_delivery.acknowledge_push),
    path('mechanics/overview/', mechanics.overview),
    path('mechanics/<int:pk>/lifts/', mechanics.lifts),
    path('mechanics/<int:pk>/lifts/export/', mechanics.export),
    path('mechanics/<int:pk>/assignments/', mechanics.assign),
    path('analytics/duty/', duty_analytics.summary),
    path('planning/notifications/<int:pk>/', planning_push.content),
    path('vacations/', vacations.requests),
    path('vacations/export/', vacations.export),
    path('vacations/<int:pk>/', vacations.detail),
    path('duty/planner/', duty_planning.draft),
    path('duty/planner-preview/', duty_planning.preview),
    path('duty/planner-publish/', duty_planning.publish),
    path('duty/roster/', roster.roster),
    path('duty/roster-settings/', roster.settings),
    path('duty/roster-publish/', roster.publish),
    path('mobile/push/', native_push.device),
    path('mobile/push/self/', self_push.feed),
    path('mobile/login/', mobile_auth.MobileLogin.as_view()),
    path('mobile/logout/', mobile_auth.MobileLogout.as_view()),
    path('mobile/sessions/', mobile_auth.MobileSessions.as_view()),
    path('mobile/sessions/<int:session_id>/revoke/', mobile_auth.MobileRevoke.as_view()),
]
for name,view in [('buildings',views.BuildingViewSet),('elevators',views.ElevatorViewSet),('technicians',views.TechnicianViewSet),('tickets',views.TicketViewSet),('maintenance',views.MaintenanceViewSet),('duty',views.DutyViewSet),('duty-swaps',views.DutySwapViewSet),('parts',views.PartViewSet),('chat',views.ChatViewSet),('documents',views.DocumentViewSet)]:
    router.register(name,view)
urlpatterns = [path('organizations/',organizations.organizations),path('organizations/switch/',organizations.switch_organization),path('organizations/join/',organizations.join_organization),path('organizations/invites/',organizations.organization_invites),path('organizations/invites/<int:invite_id>/revoke/',organizations.revoke_invite),path('organizations/members/',organizations.organization_members),path('organizations/members/create/',organizations.create_employee_account),path('organizations/members/<int:member_id>/',organizations.update_member),path('organizations/members/<int:member_id>/password-setup/', organizations.reissue_employee_password_setup),path('push/public-key/',views.push_public_key),path('push/subscription/',views.push_subscription),path('health/',views.health),path('me/',views.me),path('logout/',views.sign_out),path('dashboard/',views.dashboard),path('audit/',views.audit_events),path('',include(router.urls))]
urlpatterns = mobile_urls + urlpatterns
urlpatterns += [path('notification-preferences/',notification_preferences.preferences)]
urlpatterns += [path('updates/system/', system_updates.system_update),
                path('updates/', updates.catalogue),
                path('updates/<str:kind>/download/', updates.download_release)]
from . import media_api
from . import maintenance_pdf
from . import lift_documents, lift_document_folders
urlpatterns += [
    path('maintenance/<int:elevator_id>/journal/', maintenance_pdf.maintenance_journal),
    path('maintenance/<int:elevator_id>/journal/pdf/', maintenance_pdf.maintenance_pdf),
    path('lift-document-folders/', lift_document_folders.explorer),
    path('lift-documents/', lift_documents.documents),
    path('lift-documents/<int:document_id>/', lift_documents.remove),
    path('lift-documents/<int:document_id>/pdf/', lift_documents.pdf),
    path('lift-inspections/<int:elevator_id>/', lift_documents.inspection),
]
urlpatterns += [path('media/',media_api.catalogue),path('media/stats/',media_api.statistics),
    path('media/uploads/',media_api.upload),path('media/<uuid:asset_id>/links/',media_api.attach),
    path('media/<uuid:asset_id>/<str:variant>/',media_api.download)]


from . import commissioning, notification_inbox, message_receipts, notification_content
urlpatterns += [
    path('notifications/receipts/', message_receipts.acknowledge),
    path('mobile/push/content/', notification_content.fetch_content),
    path('notifications/', notification_inbox.inbox),
    path('notifications/counts/', notification_inbox.counts),
    path('notifications/sounds/', notification_inbox.sound_events),
    path('notifications/read-chat/', notification_inbox.read_chat),
    path('notifications/read-push/', notification_inbox.read_push),
    path('notifications/<int:notification_id>/read/', notification_inbox.mark_read),
]
urlpatterns += [
    path('commissioning/', commissioning.projects),
    path('commissioning/chat/', commissioning.team_chat),
    path('commissioning/chat/<int:message_id>/', commissioning.team_message),
    path('commissioning/chat/<int:message_id>/photos/<int:photo_id>/', commissioning.team_photo),
    path('commissioning/chat/<int:message_id>/photos/<int:photo_id>/preview/', commissioning.team_photo, {'preview': True}),
    path('commissioning/assignees/', commissioning.assignees),
    path('commissioning/<int:pk>/', commissioning.project),
    path('commissioning/<int:pk>/photos/<int:photo_id>/', commissioning.photo),
    path('commissioning/<int:pk>/photos/<int:photo_id>/preview/', commissioning.photo, {'preview': True}),
    path('commissioning/<int:pk>/sync/', commissioning.sync_record),
    path('commissioning/<int:pk>/lifts/', commissioning.add_lift),
    path('commissioning/<int:pk>/lifts/<int:lift_id>/assign/', commissioning.assign),
    path('commissioning/<int:pk>/lifts/<int:lift_id>/progress/', commissioning.update_progress),
    path('commissioning/<int:pk>/lifts/<int:lift_id>/nameplates/', commissioning.nameplates),
    path('commissioning/<int:pk>/lifts/<int:lift_id>/nameplates/<int:nameplate_id>/photo/', commissioning.nameplate_photo),
    path('commissioning/<int:pk>/lifts/<int:lift_id>/nameplates/<int:nameplate_id>/photo/preview/', commissioning.nameplate_photo, {'preview': True}),
    path('commissioning/<int:pk>/lift-requests/', commissioning.request_lift),
    path('commissioning/<int:pk>/lift-requests/<int:request_id>/decision/', commissioning.decide_lift),
    path('commissioning/<int:pk>/expenses/', commissioning.add_expense),
    path('commissioning/<int:pk>/expenses/<int:expense_id>/receipt/', commissioning.receipt),
    path('commissioning/<int:pk>/expenses/<int:expense_id>/upload/', commissioning.upload_receipt),
    path('commissioning/<int:pk>/expenses/<int:expense_id>/reimburse/', commissioning.reimburse),
    path('commissioning/<int:pk>/needs/', commissioning.add_need),
    path('commissioning/<int:pk>/needs/<int:need_id>/resolve/', commissioning.resolve_need),
    path('commissioning/<int:pk>/extra-work/', commissioning.add_extra),
    path('commissioning/<int:pk>/extra-work/<int:extra_id>/decision/', commissioning.decide_extra),
    path('commissioning/<int:pk>/messages/', commissioning.send_message),
    path('commissioning/<int:pk>/archive/', commissioning.archive_project),
]

from . import document_folders
urlpatterns += [path("document-folders/", document_folders.explorer)]

urlpatterns += [path('push/status/',webpush_health.status),path('push/test/',webpush_health.test_push),path('push/test/<int:pk>/',webpush_health.test_status),path('push/received/',webpush_health.received)]

urlpatterns += [path('push/inbox/<int:pk>/',planning_push.inbox_content)]
