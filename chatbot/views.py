import time
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from farms.models import Farm
from farms.services import session_key
from .context import farm_context
from .forms import ChatForm
from .models import Conversation, Message
from .services import answer_question
from .knowledge import library

SOURCE_HOSTS = {"ais.gov.bd", "www.ais.gov.bd", "bamis.gov.bd", "www.bamis.gov.bd", "power.larc.nasa.gov", "bmd.gov.bd", "www.bmd.gov.bd", "srdi.gov.bd", "www.srdi.gov.bd", "dam.gov.bd", "www.dam.gov.bd", "market.dam.gov.bd", "dae.gov.bd", "www.dae.gov.bd", "dae.portal.gov.bd", "knowledgebank.irri.org", "www.knowledgebank.irri.org", "irri.org", "www.irri.org"}
SOURCE_HOSTS.update(urlparse(source["url"]).hostname for source in library()["sources"].values())

def _owned_farms(request):
    return Farm.objects.filter(owner_session=request.session.session_key) if request.session.session_key else Farm.objects.none()

def _owned_conversation(request, pk):
    if not request.session.session_key:
        raise Http404
    return get_object_or_404(Conversation, pk=pk, owner_session=request.session.session_key)

def _positive_pk(value):
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (ValueError, TypeError):
        pass
    raise Http404

def _page(request, *, conversation=None, form=None, status=200):
    farms = _owned_farms(request)
    selected = None
    if conversation and conversation.farm_id:
        selected = farms.filter(pk=conversation.farm_id).first()
    elif request.GET.get("farm"):
        selected = get_object_or_404(farms, pk=_positive_pk(request.GET["farm"]))
        request.session["current_farm_id"] = selected.pk
    else:
        selected = farms.filter(pk=request.session.get("current_farm_id")).first()
    if form is None:
        form = ChatForm(farms=farms, initial={"conversation": conversation.pk if conversation else None, "farm": selected.pk if selected else None})
    history = list(reversed(conversation.messages.order_by("-created_at", "-pk")[:settings.CHATBOT_MAX_MESSAGES])) if conversation else []
    conversations = Conversation.objects.filter(owner_session=request.session.session_key)[:12] if request.session.session_key else []
    return render(request, "chatbot/chatroom.html", {"active_page": "chatbot", "conversation": conversation, "conversations": conversations, "chat_messages": history, "form": form, "selected_farm": selected, "chat_mode": "local", "chat_js": {}}, status=status)

@require_GET
def index(request):
    conversation = _owned_conversation(request, _positive_pk(request.GET["conversation"])) if request.GET.get("conversation") else None
    return _page(request, conversation=conversation)

def _json_requested(request):
    return "application/json" in request.headers.get("Accept", "") or request.headers.get("X-Requested-With") == "XMLHttpRequest"

def _error(request, form, *, conversation=None, status=400, message=None):
    if _json_requested(request):
        return JsonResponse({"error": message or _("Please check your question and farm selection."), "errors": form.errors.get_json_data()}, status=status)
    if message:
        form.add_error(None, message)
    return _page(request, conversation=conversation, form=form, status=status)

def _allowed_sources(sources):
    safe = []
    for source in (sources or [])[:6]:
        if not isinstance(source, dict) or not isinstance(source.get("url"), str):
            continue
        try:
            parsed = urlparse(source["url"])
            allowed = parsed.scheme == "https" and parsed.hostname in SOURCE_HOSTS and not parsed.username and not parsed.password and not parsed.query
        except ValueError:
            continue
        if allowed:
            safe.append({"title": str(source.get("title", ""))[:180], "url": source["url"]})
    return safe

def _serialize(message):
    return {"role": message.role, "body": message.body, "mode": message.mode, "sources": message.sources, "notice": message.notice, "created_at": message.created_at.isoformat()}

@require_POST
def send(request):
    form = ChatForm(request.POST, farms=_owned_farms(request))
    if not form.is_valid():
        return _error(request, form)
    data = form.cleaned_data
    conversation = _owned_conversation(request, data["conversation"]) if data.get("conversation") else None
    if conversation and conversation.messages.count() + 2 > settings.CHATBOT_MAX_MESSAGES:
        return _error(request, form, conversation=conversation, message=_("This conversation is full. Start a new conversation to continue."))
    owner = session_key(request)
    rate_key = f"agritwin:chat:{owner}:{int(time.time() // 60)}"
    cache.add(rate_key, 0, timeout=70)
    try:
        count = cache.incr(rate_key)
    except ValueError:
        cache.set(rate_key, 1, timeout=70)
        count = 1
    if count > settings.CHATBOT_MESSAGES_PER_MINUTE:
        response = _error(request, form, conversation=conversation, status=429, message=_("You have sent several questions. Please wait one minute and try again."))
        response["Retry-After"] = "60"
        return response
    farm = data.get("farm")
    context = farm_context(farm) if data.get("include_farm") and farm else None
    previous = list(reversed(conversation.messages.order_by("-created_at", "-pk")[:10])) if conversation else []
    history = [{"role": item.role, "content": item.body[:4000]} for item in previous]
    answer = answer_question(data["message"], history=history, farm_context=context, language=getattr(request, "LANGUAGE_CODE", "bn"))
    body = str(answer["text"])[:12000]
    mode = "local"
    with transaction.atomic():
        if conversation is None:
            conversation = Conversation.objects.create(owner_session=owner, title=" ".join(data["message"].split())[:100], farm=farm)
        elif farm != conversation.farm:
            conversation.farm = farm
        user_message = Message.objects.create(conversation=conversation, role="user", body=data["message"])
        assistant_message = Message.objects.create(conversation=conversation, role="assistant", body=body, mode=mode, sources=_allowed_sources(answer.get("sources", [])), notice=str(answer.get("notice", ""))[:1000])
        conversation.save()
    url = reverse("chatbot:index") + f"?conversation={conversation.pk}"
    if _json_requested(request):
        return JsonResponse({"conversation_id": conversation.pk, "user": _serialize(user_message), "assistant": _serialize(assistant_message), "clear_url": reverse("chatbot:clear", kwargs={"pk": conversation.pk}), "conversation_url": url})
    return redirect(url)

@require_POST
def clear(request, pk):
    conversation = _owned_conversation(request, pk)
    conversation.delete()
    messages.success(request, _("Conversation deleted."))
    return redirect("chatbot:index")
