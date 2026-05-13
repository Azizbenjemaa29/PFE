import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import (
    JsonResponse, StreamingHttpResponse,
    HttpResponse, Http404
)
from django.views.decorators.http import require_POST, require_GET

from .models import Conversation, Message
from .services.mistral_service import MistralService
from .services.export_service import ExportService


def _conversation_history(conversation, exclude_last=True):
    """Retourne l'historique sous forme de liste de dicts pour Mistral."""
    msgs = list(conversation.messages.order_by('created_at'))
    if exclude_last and msgs:
        msgs = msgs[:-1]  # slicing Python (pas ORM — l'ORM ne supporte pas qs[:-1])
    return [{'role': m.role, 'content': m.content} for m in msgs]


@login_required
def chat_page(request, conversation_id=None):
    conversations = Conversation.objects.filter(user=request.user)
    current_conversation = None
    messages = []

    if conversation_id:
        current_conversation = get_object_or_404(
            Conversation, pk=conversation_id, user=request.user
        )
        messages = current_conversation.messages.all()

    return render(request, 'chatbot/chat.html', {
        'conversations': conversations,
        'current_conversation': current_conversation,
        'messages': messages,
    })


@login_required
@require_POST
def stream_message(request):
    """
    Endpoint AJAX POST : question → SQL → Mistral → JSON response.
    Remplace le SSE pour être compatible avec le serveur de dev Django.
    """
    try:
        body = json.loads(request.body)
        question = body.get('question', '').strip()
        conversation_id = str(body.get('conversation_id', '')).strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Requête invalide'}, status=400)

    if not question:
        return JsonResponse({'error': 'Question vide'}, status=400)

    # Vérification clé API
    from django.conf import settings as dj_settings
    if not dj_settings.MISTRAL_API_KEY or dj_settings.MISTRAL_API_KEY == 'your_mistral_api_key_here':
        return JsonResponse({
            'error': 'Clé API Mistral non configurée. '
                     'Ouvrez le fichier .env et remplacez '
                     'MISTRAL_API_KEY=your_mistral_api_key_here '
                     'par votre vraie clé depuis console.mistral.ai'
        }, status=503)

    # Conversation
    if conversation_id and conversation_id.isdigit():
        try:
            conversation = Conversation.objects.get(
                pk=int(conversation_id), user=request.user
            )
        except Conversation.DoesNotExist:
            conversation = Conversation.objects.create(
                user=request.user, title=question[:80]
            )
    else:
        conversation = Conversation.objects.create(
            user=request.user, title=question[:80]
        )

    # Sauvegarder message utilisateur
    Message.objects.create(conversation=conversation, role='user', content=question)

    history = _conversation_history(conversation, exclude_last=True)

    try:
        service = MistralService()
        result  = service.process_question(question, request.user, history)

        if not result['success']:
            return JsonResponse({'error': result['answer']}, status=500)

        # Sauvegarder réponse assistant
        msg = Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=result['answer'],
            sql_query=result.get('sql_query', ''),
        )

        # Mettre à jour le titre si première réponse
        if conversation.messages.count() <= 2:
            conversation.title = question[:80]
            conversation.save(update_fields=['title', 'updated_at'])

        return JsonResponse({
            'answer':     result['answer'],
            'sql_query':  result.get('sql_query', ''),
            'chart_data': result.get('chart_data'),
            'conv_id':    conversation.id,
            'conv_title': conversation.title,
            'msg_id':     msg.id,
        })

    except Exception as e:
        return JsonResponse({'error': f'Erreur serveur : {e}'}, status=500)


def _sse(event_type: str, **data) -> str:
    """Construit un message SSE formaté."""
    payload = {'type': event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@login_required
@require_POST
def new_conversation(request):
    conv = Conversation.objects.create(
        user=request.user,
        title='Nouvelle conversation',
    )
    return JsonResponse({'id': conv.id, 'title': conv.title})


@login_required
@require_GET
def get_conversations(request):
    convs = list(
        Conversation.objects.filter(user=request.user)
        .values('id', 'title', 'updated_at')
    )
    return JsonResponse({'conversations': convs}, json_dumps_params={'default': str})


@login_required
def delete_conversation(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    conv = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    conv.delete()
    return JsonResponse({'success': True})


@login_required
def export_markdown(request, conversation_id):
    conv = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    service = ExportService()
    content = service.export_markdown(conv)

    safe_title = conv.title.replace(' ', '_')[:50]
    response = HttpResponse(content, content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{safe_title}.md"'
    return response


@login_required
def export_pdf(request, conversation_id):
    conv = get_object_or_404(Conversation, pk=conversation_id, user=request.user)

    try:
        service = ExportService()
        buffer = service.export_pdf(conv)
        safe_title = conv.title.replace(' ', '_')[:50]
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{safe_title}.pdf"'
        return response
    except ImportError as e:
        return HttpResponse(str(e), status=500, content_type='text/plain')
