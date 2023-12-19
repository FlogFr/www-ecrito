from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.images.blocks import ImageChooserBlock


class HeroBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    image = ImageChooserBlock(required=True)
    description = blocks.RichTextBlock()
    herotype = blocks.ChoiceBlock(choices=[
        ('ce', 'Centered Background'),
        ('cs', 'Centered Screenshot'),
        ('rla', 'Responsive Left Aligned'),
        ('rra', 'Responsive Right Aligned'),
        ('vlc', 'Vertically Left Centered'),
        ('vrc', 'Vertically Right Centered'),
    ])

    class Meta:
        icon = 'heading'
        classname = 'hero'


class GeolocLeafletBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=True)
    description = blocks.RichTextBlock(required=False)
    lat = blocks.DecimalBlock(required=True, min_value=-90.00, max_value=90.00)
    lon = blocks.DecimalBlock(required=True, min_value=-180.00, max_value=180.00)

    class Meta:
        classname = 'geoloc'


class DividerBlock(blocks.StructBlock):
    dividertype = blocks.ChoiceBlock(choices=[
        ('small', 'Small Divider'),
        ('medium', 'Medium Divider'),
        ('large', 'Large Divider'),
    ])

    class Meta:
        classname = 'divider'


class PostPage(Page):
    body = StreamField([
        ('heading', blocks.CharBlock(form_classname="title")),
        ('geoloc', GeolocLeafletBlock()),
        ('carousel', blocks.StreamBlock([
            ('image', ImageChooserBlock()),
        ])),
        ('paragraph', blocks.RichTextBlock()),
        ('image', ImageChooserBlock()),
        ('hero', HeroBlock()),
        ('divider', DividerBlock()),
    ], use_json_field=True)

    content_panels = Page.content_panels + [
        FieldPanel('body'),
    ]


class HomePage(Page):
    body = StreamField([
        ('heading', blocks.CharBlock(form_classname="title")),
        ('geoloc', GeolocLeafletBlock()),
        ('carousel', blocks.StreamBlock([
            ('image', ImageChooserBlock()),
        ])),
        ('paragraph', blocks.RichTextBlock()),
        ('image', ImageChooserBlock()),
        ('hero', HeroBlock()),
        ('divider', DividerBlock()),
    ], use_json_field=True)

    content_panels = Page.content_panels + [
        FieldPanel('body'),
    ]

    def get_posts(self):
        return PostPage.objects.all()
