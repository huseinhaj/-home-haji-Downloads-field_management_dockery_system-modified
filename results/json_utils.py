"""Msimbo wa JSON unaotumia alama za Decimal.

Alama sasa ni Decimal (10.60) ili zisioneweze kupotea. DjangoJSONEncoder
ya kawaida huandika Decimal kama **string** ("10.60"), na hiyo ni
hatari kwenye JavaScript: `marks[sid] > 50` inalingana na kamba
("10.60" > 50 ni kweli, lakini "9.00" > 50 ni SIKWELI) — kwa hiyo
majaribio ya kipimo chafu zinapoteleza.

Hapa tunafanya Decimal iwe namba halisi ndani ya JSON. Uhakika wa
kitoshi unabaki kwenye database (DecimalField); kwenye JSON tuna
tuma float, ambayo ni sahihi kwa alama za 0–100 na maeneo mawili ya
decimal.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder


class ScoreJSONEncoder(DjangoJSONEncoder):
    """DjangoJSONEncoder ambayo huandika Decimal kama namba, si kamba."""

    def default(self, o):
        if isinstance(o, Decimal):
            # float(...) ni safi kwa Decimal yenye maeneo ya decimal, na
            # ukibadilisha kuwa int unapopata 10.60 -> 10 au 0.6 -> 0
            # (kutoka kwa kukosewa namba, kama 10.678 inayokataa hata).
            return float(o)
        return super().default(o)
