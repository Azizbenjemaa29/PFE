from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('', views.chat_page, name='chat'),
    path('<int:conversation_id>/', views.chat_page, name='chat_with_id'),

    # API endpoints
    path('api/stream/', views.stream_message, name='stream_message'),
    path('api/new/', views.new_conversation, name='new_conversation'),
    path('api/conversations/', views.get_conversations, name='get_conversations'),
    path('api/delete/<int:conversation_id>/', views.delete_conversation, name='delete_conversation'),

    # Export
    path('export/md/<int:conversation_id>/', views.export_markdown, name='export_md'),
    path('export/pdf/<int:conversation_id>/', views.export_pdf, name='export_pdf'),
]
