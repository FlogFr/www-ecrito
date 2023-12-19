from django import template
from django.shortcuts import resolve_url
from django.template.defaulttags import token_kwargs
from django.template.loader import render_to_string
from django.utils.encoding import force_str
from django.utils.html import conditional_escape

from home import models

register = template.Library()

@register.filter(name="get_lon", takes_context=False)
def get_children_menu_live(page, fallback=None):
    if not isinstance(page, models.PostPage):
        raise ValueError("get_lon tag expected a PostPage object, got %r" % page)

    return page.body[0].value["lon"]

@register.filter(name="get_lat", takes_context=False)
def get_children_menu_live(page, fallback=None):
    if not isinstance(page, models.PostPage):
        raise ValueError("get_lat tag expected a PostPage object, got %r" % page)

    return page.body[0].value["lat"]
