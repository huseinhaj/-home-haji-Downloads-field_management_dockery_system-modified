"""
gepg.py — GePG (Government e-Payment Gateway, Tanzania) real integration.

Flow (GePG v2, kama ilivyoelezwa kwenye GePG Integration Guide na
kuthibitishwa dhidi ya reference library ya watabelabs/gepg-java):

  1. BILL SUBMISSION (kuzalisha control number)
     Tunatuma <gepgBillSubReq> (XML iliyotiwa sahihi ya digital, ndani ya
     envelope ya <Gepg> yenye <gepgSignature>) kwenye endpoint ya GePG
     (/api/bill/sigqrequest). GePG inarudisha <gepgBillSubResp> iliyo na
     ControlNum (namba ya malipo ya tarakimu 10).

  2. PAYMENT
     Mwanafunzi analipa kupitia njia yoyote ya PSP (benki / simu ya
     mkonomi / GePG channels) akitaja namba ya malipo (control number).

  3. CONFIRMATION (reconciliation)
     GePG inasukumia taarifa ya malipo kwenye webhook yetu
     (/ttc/api/gepg/notification/) — inashughulikiwa na
     handle_payment_notification() — au SP inaweza kuuliza status
     (/api/sp/statusRequest) kupitia check_payment_status().

Maombi yote yanatiwa sahihi ya digital na private key ya PSP
(SHA1withRSA — default ya GePG) na kutumwa kwa HTTPS na mutual TLS
(client certificate). Credentials zinapatikana baada ya PSP registration
na GePG — tazama README (sehemu ya "GePG (halisi)").

Credential zisipokuwepo, mfumo unatumia simulated control numbers
(services.generate_control_number) kiotomatiki — portal inaendelea
kufanya kazi hadi onboarding ya GePG ikamilike.
"""

import base64
import json
import logging
import re
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone
from lxml import etree

logger = logging.getLogger(__name__)

# GePG v2 endpoints (kutoka GePG Integration Guide / gepg-java)
ENDPOINT_SUBMIT_BILL = '/api/bill/sigqrequest'
ENDPOINT_REUSE_CONTROL = '/api/bill/sigqrequest_reuse'
ENDPOINT_UPDATE_BILL = '/api/bill/sigqrequest_change'
ENDPOINT_CANCEL_BILL = '/api/bill/sigcancel_request'
ENDPOINT_RECONCILIATION = '/api/reconciliations/sig_sp_qrequest'
ENDPOINT_SEND_PAYMENT = '/api/sp/paymentRequest'
ENDPOINT_CHECK_STATUS = '/api/sp/statusRequest'

# GePG status codes
CODE_SUCCESS = '7101'


# ── Configuration ─────────────────────────────────────────────────────────────

def _get(name, default=''):
    return getattr(settings, name, default)


def gepg_enabled():
    """True ikiwa credentials za GePG zimewekwa (onboarding imekamilika)."""
    return bool(
        getattr(settings, 'TTC_GEPG_ENABLED', False)
        and _get('TTC_GEPG_CODE')
        and _get('TTC_GEPG_API_URL')
        and (_get('TTC_GEPG_PRIVATE_KEY_PATH') or _get('TTC_GEPG_CLIENT_KEY'))
    )


def gepg_mode_label():
    return 'GePG (halisi)' if gepg_enabled() else 'Simulated (GePG bado haijasanidiwa)'


# ── Ujenzi wa XML ya bill ─────────────────────────────────────────────────────

def build_bill_xml(bill, bill_id=None):
    """Tengeneza <gepgBillSubReq> (inner XML) kwa FeeBill — muundo wa GePG.

    Returns (xml_string, bill_id).
    """
    bill_id = bill_id or bill.gepg_bill_id or str(uuid.uuid4())
    sp_code = _get('TTC_GEPG_CODE')
    sub_sp_code = _get('TTC_GEPG_SUB_SP_CODE', '')
    sp_sys_id = _get('TTC_GEPG_SP_SYS_ID', '')
    gfs_code = _get('TTC_GEPG_GFS_CODE', '')
    lifetime_days = getattr(settings, 'TTC_CONTROL_NUMBER_LIFETIME_DAYS', 30)
    now = timezone.now()

    amount = f'{float(bill.amount):.2f}'
    expr_dt = (now + timedelta(days=lifetime_days)).strftime('%Y-%m-%dT%H:%M:%S')
    gen_dt = now.strftime('%Y-%m-%dT%H:%M:%S')

    student = bill.student
    payer_name = (student.full_name or 'Student')[:100]
    payer_phone = re.sub(r'\D', '', student.phone_number or '')[:12] or '0000000000'
    payer_email = (student.email or '')[:100]
    payer_id = (student.registration_number or f'STU{bill.student_id}')[:20]
    bill_desc = f'{bill.fee_item.name} {bill.academic_year}'[:255]

    def el(parent, tag, text):
        node = etree.Element(tag)
        node.text = text
        parent.append(node)

    root = etree.Element('gepgBillSubReq')

    hdr = etree.Element('BillHdr')
    el(hdr, 'SpCode', sp_code)
    el(hdr, 'RtrRespFlg', 'true')
    root.append(hdr)

    trx = etree.Element('BillTrxInf')
    el(trx, 'BillId', bill_id)
    el(trx, 'SubSpCode', sub_sp_code)
    el(trx, 'SpSysId', sp_sys_id)
    el(trx, 'BillAmt', amount)
    el(trx, 'MiscAmt', '0.00')
    el(trx, 'BillExprDt', expr_dt)
    el(trx, 'PyrId', payer_id)
    el(trx, 'PyrName', payer_name)
    el(trx, 'BillDesc', bill_desc)
    el(trx, 'BillGenDt', gen_dt)
    el(trx, 'BillPayOpt', '1')
    el(trx, 'UsrId', sp_sys_id or 'system')
    el(trx, 'PyrPhone', payer_phone)
    el(trx, 'PyrEmail', payer_email)
    el(trx, 'Currency', 'TZS')
    el(trx, 'BillEqvAmt', amount)
    el(trx, 'RemFlag', 'true')

    items = etree.Element('BillItems')
    item = etree.Element('BillItem')
    el(item, 'BillItemRef', bill_id)
    el(item, 'UseItemRefOnPay', 'N')
    el(item, 'BillItemAmt', amount)
    el(item, 'BillItemEqvAmt', amount)
    el(item, 'BillItemMiscAmt', '0.00')
    el(item, 'GfsCode', gfs_code)
    items.append(item)
    trx.append(items)
    root.append(trx)

    xml = etree.tostring(root, encoding='unicode', pretty_print=False)
    return xml, bill_id


# ── Digital signature (RSA) ───────────────────────────────────────────────────

def _load_private_key():
    """Pakia private key — inaweza kuwa PEM (PKCS#8/PKCS#1) au PKCS#12 (.pfx)."""
    from cryptography.hazmat.primitives import serialization

    path = _get('TTC_GEPG_PRIVATE_KEY_PATH')
    password = _get('TTC_GEPG_PRIVATE_KEY_PASSWORD') or None
    password_bytes = password.encode('utf-8') if password else None

    with open(path, 'rb') as fh:
        data = fh.read()

    try:
        return serialization.load_pem_private_key(data, password=password_bytes)
    except (ValueError, TypeError):
        pass

    # PKCS#12 (.pfx/.p12)
    try:
        key, _cert, _extra = serialization.pkcs12.load_key_and_certificates(
            data, password_bytes
        )
        if key is None:
            raise ValueError('PKCS#12 haina private key')
        return key
    except Exception as exc:
        raise RuntimeError(
            f'Imeshindikana kupakia GePG private key ({path}): {exc}'
        ) from exc


def _sign(inner_xml):
    """Tia sahihi ya RSA (PKCS#1 v1.5) kwenye inner XML — GePG default SHA1."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _load_private_key()
    algo = _get('TTC_GEPG_SIGNATURE_ALGORITHM', 'SHA1withRSA').upper()
    if 'SHA512' in algo:
        hash_algo = hashes.SHA512()
    elif 'SHA256' in algo:
        hash_algo = hashes.SHA256()
    else:
        hash_algo = hashes.SHA1()

    signature = key.sign(
        inner_xml.encode('utf-8'), padding.PKCS1v15(), hash_algo
    )
    return base64.b64encode(signature).decode('ascii')


def build_request_payload(inner_xml):
    """Funga inner XML + signature ndani ya envelope ya <Gepg> (muundo wa GePG)."""
    signature = _sign(inner_xml)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Gepg>\n'
        f'{inner_xml}\n'
        f'<gepgSignature>{signature}</gepgSignature>\n'
        '</Gepg>'
    )


# ── HTTP (mTLS + basic auth) ──────────────────────────────────────────────────

def _post(path, payload_xml, headers_extra=None):
    """Tuma XML kwa GePG kwa HTTPS na client certificate (mTLS)."""
    url = _get('TTC_GEPG_API_URL').rstrip('/') + path
    headers = {'Content-Type': 'Application/xml'}
    headers.update(headers_extra or {})

    cert = None
    if _get('TTC_GEPG_CLIENT_CERT') and _get('TTC_GEPG_CLIENT_KEY'):
        cert = (_get('TTC_GEPG_CLIENT_CERT'), _get('TTC_GEPG_CLIENT_KEY'))

    auth = None
    if _get('TTC_GEPG_API_USER'):
        auth = (_get('TTC_GEPG_API_USER'), _get('TTC_GEPG_API_PASSWORD'))

    resp = requests.post(
        url,
        data=payload_xml.encode('utf-8'),
        headers=headers,
        cert=cert,
        auth=auth,
        timeout=getattr(settings, 'TTC_GEPG_TIMEOUT', 30),
    )
    resp.raise_for_status()
    return resp.text


# ── Parsing ya majibu ya GePG ─────────────────────────────────────────────────

def _root(text):
    try:
        return etree.fromstring(text.encode('utf-8'))
    except (etree.XMLSyntaxError, ValueError):
        return None


def parse_bill_response(response_xml):
    """Toa ControlNum (tarakimu 10) kutoka response ya GePG (gepgBillSubResp)."""
    root = _root(response_xml)
    if root is not None:
        for el in root.iter():
            tag = etree.QName(el).localname.lower()
            if tag.endswith('controlnum') and el.text and el.text.strip():
                return el.text.strip()
        # Wakati mwingine GePG inaweka control number kwenye BillId/BillRef
        for el in root.iter():
            tag = etree.QName(el).localname.lower()
            if tag in ('billid', 'billref') and el.text and re.fullmatch(r'\d{10}', el.text.strip()):
                return el.text.strip()
    # Fallback: namba yoyote ya tarakimu 10 kwenye response
    m = re.search(r'\b\d{10}\b', response_xml or '')
    return m.group(0) if m else None


def extract_status_code(response_xml):
    """Toa GePG status code (mf. 7101/7201) kutoka response yoyote."""
    root = _root(response_xml)
    if root is None:
        return None
    for el in root.iter():
        tag = etree.QName(el).localname.lower()
        if tag in ('trxstscode', 'stscode', 'statuscode') and el.text and el.text.strip():
            return el.text.strip()
    return None


def check_payment_status(control_number):
    """Uliza GePG kuhusu malipo ya control number (statusRequest).

    Returns raw XML response. Schema halisi inathibitishwa na timu ya GePG
    wakati wa onboarding (kawaida <gepgSpReconcReq>/<gepgSpStatusReq>).
    """
    bill_id = control_number
    inner_xml = (
        '<gepgSpStatusReq>'
        f'<BillId>{bill_id}</BillId>'
        f'<ControlNum>{control_number}</ControlNum>'
        '</gepgSpStatusReq>'
    )
    payload = build_request_payload(inner_xml)
    return _post(ENDPOINT_CHECK_STATUS, payload)


# ── Payment notification (webhook) ────────────────────────────────────────────

def _flatten_payload(payload):
    """Rahisisha XML au JSON → {localname_lower: text} kwa parsing rahisi."""
    if isinstance(payload, dict):
        return {str(k).lower(): str(v) for k, v in payload.items()}

    text = (
        payload
        if isinstance(payload, str)
        else payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)
    ).strip()

    if text.startswith('{'):
        try:
            return {str(k).lower(): str(v) for k, v in json.loads(text).items()}
        except json.JSONDecodeError:
            pass

    root = _root(text)
    if root is None:
        return {}
    out = {}
    for el in root.iter():
        tag = etree.QName(el).localname.lower()
        if el.text and el.text.strip():
            out.setdefault(tag, el.text.strip())
    return out


def _first(data, keys):
    for key in keys:
        if key in data and data[key]:
            return data[key]
    return None


def _parse_amount(value):
    try:
        return float(re.sub(r'[^\d.]', '', str(value)) or 0)
    except ValueError:
        return 0.0


def _map_method(raw):
    raw = (raw or '').lower()
    if any(k in raw for k in ('bank', 'nmb', 'crdb', 'nbc', 'boa', 'tpb', 'equity')):
        return 'bank'
    if any(k in raw for k in ('mpesa', 'm-pesa', 'tigo', 'airtel', 'halopesa', 'mobile')):
        return 'mobile'
    return 'other'


def handle_payment_notification(payload):
    """Chakata taarifa ya malipo ya GePG (push) → thibitisha bili inayolingana.

    GePG inatuma taarifa ya malipo kwenye callback URL yetu. Majina ya
    elementi yanaweza kutofautiana kidogo kati ya deployments; tuna-tafuta
    majina ya kawaida ili onboarding na GePG iwe tu kubadilisha config.

    Returns (bill, payment, created) au (None, None, False) ikiwa control
    number haijulikani.
    """
    from .models import FeeBill, Payment

    data = _flatten_payload(payload)

    control_number = _first(data, ['controlnum', 'billid', 'controlnumber', 'billnumber'])
    if not control_number:
        logger.warning('GePG notification: hakuna control number kwenye payload.')
        return None, None, False
    control_number = control_number.strip()

    bill = (
        FeeBill.objects
        .filter(control_number=control_number)
        .select_related('student', 'fee_item')
        .first()
    )
    if bill is None:
        logger.warning('GePG notification: control number %s haijulikani.', control_number)
        return None, None, False

    amount_raw = _first(data, ['pyramt', 'paidamt', 'trxamt', 'billamt', 'amount'])
    amount = _parse_amount(amount_raw) if amount_raw else float(bill.amount)
    reference = _first(
        data, ['receiptnumber', 'trxid', 'transactionid', 'pspreceipt', 'billref']
    ) or control_number
    channel = _first(data, ['pspname', 'channel', 'paychnl', 'pspcode', 'trxchannel'])
    method = _map_method(channel)
    notes = f'GePG auto-reconciled ({channel or "GePG"})'

    # Idempotent — usiunde malipo mara mbili kwa kumbukumbu ile ile
    existing = Payment.objects.filter(bill=bill, reference=reference).first()
    if existing:
        return bill, existing, False

    payment = Payment.objects.create(
        bill=bill,
        student=bill.student,
        amount=amount,
        method=method,
        reference=reference,
        status='confirmed',
        notes=notes,
        confirmed_at=timezone.now(),
    )

    from .services import refresh_bill_status
    refresh_bill_status(bill)
    logger.info(
        'GePG malipo yamethibitishwa kiotomatiki: %s TZS %s (%s)',
        control_number, amount, channel or '?',
    )
    return bill, payment, True


# ── Bill submission (control number) ──────────────────────────────────────────

def submit_bill(bill):
    """Wasilisha bili kwa GePG na urudishe control number (tarakimu 10).

    Returns control number. Raises ikiwa GePG haikurudisha namba — mwita
    anaamua fallback.
    """
    inner_xml, bill_id = build_bill_xml(bill)
    payload = build_request_payload(inner_xml)
    logger.info('GePG bill submission: bill=%s bill_id=%s', bill.pk, bill_id)

    response_xml = _post(ENDPOINT_SUBMIT_BILL, payload)

    control_number = parse_bill_response(response_xml)
    if not control_number:
        code = extract_status_code(response_xml)
        raise ValueError(
            f'GePG hakurudisha control number (TrxStsCode={code or "?"}). '
            f'Response: {response_xml[:500]}'
        )

    # Hifadhi BillId ya GePG kwa ajili ya update/cancel/reuse baadaye
    bill.gepg_bill_id = bill_id
    bill.save(update_fields=['gepg_bill_id'])
    return control_number
