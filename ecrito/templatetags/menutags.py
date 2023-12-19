from django import template
from django.shortcuts import resolve_url
from django.template.defaulttags import token_kwargs
from django.template.loader import render_to_string
from django.utils.encoding import force_str
from django.utils.html import conditional_escape

from wagtail.models import Page

register = template.Library()

@register.filter(name="get_children_menu_live", takes_context=False)
def get_children_menu_live(page, fallback=None):
    if not isinstance(page, Page):
        raise ValueError("pageurl tag expected a Page object, got %r" % page)

    return page.get_children().filter(show_in_menus=True).live()
