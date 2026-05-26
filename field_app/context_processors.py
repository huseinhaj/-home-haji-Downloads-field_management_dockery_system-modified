def language(request):
    """
    Adds current UI language to every template context.
    Default: 'en' (English). User can switch to 'sw' (Swahili).
    Stored in session so preference persists across pages.
    """
    lang = request.session.get('ui_lang', 'en')
    return {'LANG': lang}
