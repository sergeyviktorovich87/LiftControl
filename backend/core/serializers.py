from django.utils import timezone
from rest_framework import serializers
from .models import Building, Elevator, Maintenance, Technician, Ticket, DutyShift, PartRequest, ChatMessage, Document
from .access import org, manager, technician_id


class TenantSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        organization = org(self.context['request'].user)
        for key in ('building','elevator','assigned_technician','assigned_to','technician'):
            item = attrs.get(key)
            if item is not None and item.organization_id != organization.id:
                raise serializers.ValidationError({key: 'Объект другой организации недоступен.'})
        return attrs


class BuildingSerializer(TenantSerializer):
    elevators_count = serializers.IntegerField(source='elevators.count', read_only=True)
    class Meta:
        model = Building
        fields = '__all__'
        read_only_fields = ['organization']


class TechnicianSerializer(TenantSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    class Meta:
        model = Technician
        exclude = ['last_latitude','last_longitude','last_location_at']
        read_only_fields = ['organization']


class ElevatorSerializer(TenantSerializer):
    address = serializers.CharField(source='building.address', read_only=True)
    building_name = serializers.CharField(source='building.name', read_only=True)
    technician_name = serializers.CharField(source='assigned_technician.full_name', read_only=True, default='')
    class Meta:
        model = Elevator
        fields = '__all__'
        read_only_fields = ['organization']


class TicketSerializer(TenantSerializer):
    address = serializers.CharField(source='elevator.building.address', read_only=True)
    elevator_factory_number = serializers.CharField(source='elevator.factory_number', read_only=True)
    technician_name = serializers.CharField(source='assigned_to.full_name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    photos = serializers.SerializerMethodField()
    def get_photos(self, obj):
        return [{'id':p.pk, 'url':f'/api/tickets/{obj.pk}/photos/{p.pk}/'} for p in obj.photos.filter(deleted_at__isnull=True)]
    class Meta:
        model = Ticket
        fields = '__all__'
        read_only_fields = ['organization','completed_at','created_at','updated_at']
    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context['request'].user
        if not manager(user):
            if self.instance and self.instance.assigned_to_id != technician_id(user):
                raise serializers.ValidationError('Можно изменять только свои заявки.')
            if self.instance and any(k not in ('repair','status') for k in attrs):
                raise serializers.ValidationError('Механик может изменять только статус и результат своих работ.')
            if not self.instance:
                attrs['assigned_to_id'] = technician_id(user)
                attrs.pop('assigned_to',None)
        status = attrs.get('status', getattr(self.instance,'status','NEW'))
        if status == 'DONE':
            repair = attrs.get('repair',getattr(self.instance,'repair','')).strip()
            assignee = attrs.get('assigned_to',getattr(self.instance,'assigned_to',None)) or attrs.get('assigned_to_id')
            if not repair or not assignee:
                raise serializers.ValidationError('Для завершения нужны исполнитель и выполненные работы.')
            attrs['completed_at'] = getattr(self.instance,'completed_at',None) or timezone.now()
        elif self.instance and self.instance.status == 'DONE':
            attrs['completed_at'] = None
        return attrs


class MaintenanceSerializer(TenantSerializer):
    address = serializers.CharField(source='elevator.building.address', read_only=True)
    elevator_factory_number = serializers.CharField(source='elevator.factory_number', read_only=True)
    technician_name = serializers.CharField(source='technician.full_name', read_only=True, default='')
    class Meta:
        model = Maintenance
        fields = '__all__'
        read_only_fields = ['organization']
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('completed_at',getattr(self.instance,'completed_at',None)) and not attrs.get('notes',getattr(self.instance,'notes','')).strip():
            raise serializers.ValidationError('Для выполненной работы нужен результат в журнале.')
        if not manager(self.context['request'].user):
            tid = technician_id(self.context['request'].user)
            if self.instance and self.instance.technician_id != tid:
                raise serializers.ValidationError('Недоступно редактирование чужой записи.')
            if self.instance and any(k not in ('notes','completed_at') for k in attrs):
                raise serializers.ValidationError('Можно изменить только результат и время выполнения.')
            if not self.instance:
                attrs.pop('technician',None)
                attrs['technician_id'] = tid
        return attrs


class DutySerializer(TenantSerializer):
    technician_name = serializers.CharField(source='technician.full_name', read_only=True)
    class Meta:
        model = DutyShift
        fields = '__all__'
        read_only_fields = ['organization','updated_at']
    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get('start',getattr(self.instance,'start',None))
        end = attrs.get('end',getattr(self.instance,'end',None))
        if not start or not end or not 0 < (end-start).total_seconds() <= 86400:
            raise serializers.ValidationError('Дежурство должно длиться от 1 минуты до 24 часов.')
        tech = attrs.get('technician',getattr(self.instance,'technician',None))
        if not tech or not tech.active:
            raise serializers.ValidationError('Выберите действующего механика.')
        q = DutyShift.objects.filter(organization=org(self.context['request'].user),technician=tech,start__lt=end,end__gt=start)
        if self.instance:
            q = q.exclude(pk=self.instance.pk)
        if q.exists():
            raise serializers.ValidationError('У сотрудника уже есть пересекающееся дежурство.')
        return attrs


class PartSerializer(TenantSerializer):
    address = serializers.CharField(source='elevator.building.address', read_only=True)
    elevator_factory_number = serializers.CharField(source='elevator.factory_number', read_only=True)
    author_name = serializers.SerializerMethodField()
    def get_author_name(self,obj):
        return (obj.requested_by.get_full_name() or obj.requested_by.username) if obj.requested_by else 'Удалённый пользователь'
    class Meta:
        model = PartRequest
        fields = '__all__'
        read_only_fields = ['organization','requested_by','created_at','updated_at']
    def validate(self,attrs):
        attrs = super().validate(attrs)
        user = self.context['request'].user
        if not manager(user):
            if self.instance and (self.instance.requested_by_id != user.id or self.instance.status != 'NEW'):
                raise serializers.ValidationError('Можно редактировать только свою новую заявку.')
            if 'status' in attrs and attrs['status'] != 'NEW':
                raise serializers.ValidationError('Статус меняет руководитель или диспетчер.')
        if attrs.get('quantity',1) < 1:
            raise serializers.ValidationError({'quantity':'Количество должно быть больше нуля.'})
        return attrs


class ChatSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    def get_author_name(self,obj):
        return (obj.author.get_full_name() or obj.author.username) if obj.author else 'Удалённый пользователь'
    class Meta:
        model = ChatMessage
        fields = ['id','body','author','author_name','created_at']
        read_only_fields = ['id','author','created_at']


class DocumentSerializer(TenantSerializer):
    url = serializers.SerializerMethodField()
    def get_url(self,obj):
        return f'/api/documents/{obj.pk}/download/'
    class Meta:
        model = Document
        fields = ['id','title','manufacturer','model','url','created_at']
        read_only_fields = ['created_at']
