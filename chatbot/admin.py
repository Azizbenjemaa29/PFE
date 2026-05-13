from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('role', 'content', 'sql_query', 'created_at')
    fields = ('role', 'content', 'sql_query', 'created_at')
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'updated_at', 'message_count')
    list_filter = ('user', 'created_at')
    search_fields = ('title', 'user__nom')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MessageInline]

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'role', 'short_content', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('content', 'conversation__title')
    readonly_fields = ('created_at',)

    def short_content(self, obj):
        return obj.content[:80]
    short_content.short_description = 'Contenu'
