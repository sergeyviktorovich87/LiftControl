from django.contrib import admin
from .models import Building, Elevator, Maintenance, Technician, Ticket

@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('address', 'name', 'management_company')
    search_fields = ('address', 'name', 'management_company')

@admin.register(Elevator)
class ElevatorAdmin(admin.ModelAdmin):
    list_display = ('factory_number', 'building', 'entrance', 'manufacturer', 'model', 'assigned_technician', 'active')
    list_filter = ('active', 'elevator_type', 'manufacturer')
    search_fields = ('factory_number', 'building__address', 'model', 'manufacturer')

@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'role', 'phone', 'active')
    list_filter = ('role', 'active')
    search_fields = ('full_name', 'phone')

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    # The admin must not bypass append-only audited ticket state transitions.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    list_display = ('id', 'elevator', 'title', 'priority', 'status', 'assigned_to', 'created_at')
    list_filter = ('priority', 'status')
    search_fields = ('title', 'description', 'elevator__factory_number', 'elevator__building__address')

@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('planned_date', 'kind', 'elevator', 'technician', 'completed_at')
    list_filter = ('kind', 'planned_date')


from .models import Organization, Membership, DutyShift, PartRequest, ChatMessage, Document, TicketPhoto, AuditEvent, TicketEvent, TicketComment, PushSubscription, PushDelivery
admin.site.register(Organization)
admin.site.register(Membership)

class HistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):
        return False
    def has_change_permission(self,request,obj=None):
        return False
    def has_delete_permission(self,request,obj=None):
        return False

for model in (DutyShift, PartRequest, ChatMessage, Document, TicketPhoto, AuditEvent, TicketEvent, TicketComment, PushDelivery):
    admin.site.register(model,HistoryAdmin)
