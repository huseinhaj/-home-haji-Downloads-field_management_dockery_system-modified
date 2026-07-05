"""billing_views.py — School subscription plans + ClickPesa checkout.

Generating official/general results (finalize, PDF, Excel) is gated on
SchoolSubscription.is_active. Nothing here marks a payment as
successful on its own — only the ClickPesa webhook (payment_webhook)
does that, once ClickPesa confirms the mobile money charge actually
went through.
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import PaymentTransaction, SchoolSubscription, SubscriptionPlan
from .permissions import academic_required
from .services.clickpesa_service import ClickPesaError, initiate_ussd_push, normalize_tz_phone


@academic_required
def choose_plan(request):
    school = request.user.school
    subscription, _ = SchoolSubscription.objects.get_or_create(school=school)
    plans = SubscriptionPlan.objects.filter(is_active=True)
    return render(request, 'results/choose_plan.html', {
        'school': school,
        'subscription': subscription,
        'plans': plans,
    })


@academic_required
def pay_for_plan(request, plan_id):
    school = request.user.school
    plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

    if request.method == 'POST':
        raw_phone = request.POST.get('phone_number', '').strip()
        phone_number = normalize_tz_phone(raw_phone)
        if len(phone_number) != 12:
            messages.error(request, "Namba ya simu si sahihi. Tumia mfano 0712345678.")
            return redirect('pay_for_plan', plan_id=plan.id)

        order_reference = f"SCH{school.id}{uuid.uuid4().hex[:10].upper()}"
        transaction = PaymentTransaction.objects.create(
            school=school, plan=plan, initiated_by=request.user,
            phone_number=phone_number, order_reference=order_reference,
            amount=plan.price_tzs,
        )
        try:
            response = initiate_ussd_push(amount=plan.price_tzs, phone_number=phone_number, order_reference=order_reference)
        except ClickPesaError as exc:
            transaction.status = PaymentTransaction.STATUS_FAILED
            transaction.raw_response = {'error': str(exc)}
            transaction.save(update_fields=['status', 'raw_response'])
            messages.error(request, str(exc))
            return redirect('pay_for_plan', plan_id=plan.id)

        transaction.clickpesa_payment_id = response.get('id', '')
        transaction.status = PaymentTransaction.STATUS_PROCESSING
        transaction.raw_response = response
        transaction.save(update_fields=['clickpesa_payment_id', 'status', 'raw_response'])

        messages.success(request, "Ombi la malipo limetumwa. Angalia simu yako uthibitishe kwa PIN yako.")
        return redirect('payment_pending', transaction_id=transaction.id)

    return render(request, 'results/pay_for_plan.html', {'school': school, 'plan': plan})


@academic_required
def payment_pending(request, transaction_id):
    transaction = get_object_or_404(PaymentTransaction, id=transaction_id, school=request.user.school)
    return render(request, 'results/payment_pending.html', {'transaction': transaction})


@academic_required
def payment_status_json(request, transaction_id):
    transaction = get_object_or_404(PaymentTransaction, id=transaction_id, school=request.user.school)
    return JsonResponse({'status': transaction.status})


@csrf_exempt
@require_POST
def payment_webhook(request):
    """ClickPesa POSTs here on payment events. We only trust status changes
    that arrive through this webhook — never mark a transaction SUCCESS
    from the initiate-payment response, since that's just "processing"."""
    import json

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid JSON'}, status=400)

    data = payload.get('data', {})
    order_reference = data.get('orderReference')
    status = data.get('status')
    if not order_reference or not status:
        return JsonResponse({'error': 'missing orderReference/status'}, status=400)

    try:
        transaction = PaymentTransaction.objects.get(order_reference=order_reference)
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'error': 'unknown orderReference'}, status=404)

    transaction.status = status if status in dict(PaymentTransaction.STATUS_CHOICES) else transaction.status
    transaction.clickpesa_payment_id = data.get('id', transaction.clickpesa_payment_id)
    transaction.raw_response = payload
    transaction.save(update_fields=['status', 'clickpesa_payment_id', 'raw_response'])

    if transaction.status == PaymentTransaction.STATUS_SUCCESS:
        subscription, _ = SchoolSubscription.objects.get_or_create(school=transaction.school)
        base = subscription.active_until if subscription.active_until and subscription.active_until > timezone.now() else timezone.now()
        subscription.active_until = base + timezone.timedelta(days=transaction.plan.duration_days)
        subscription.plan = transaction.plan
        subscription.save(update_fields=['active_until', 'plan'])

    return JsonResponse({'received': True})
