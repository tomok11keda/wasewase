from django import forms
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


class ImagePickWidget(forms.ClearableFileInput):
    """Hide the browser file control; show camera / library action buttons."""

    template_name = "widgets/image_pick_input.html"

    def __init__(self, attrs=None):
        base = {"accept": "image/*", "class": "image-pick__native"}
        if attrs:
            merged = {**base, **attrs}
            extra_class = attrs.get("class")
            if extra_class:
                merged["class"] = f"image-pick__native {extra_class}".strip()
            base = merged
        super().__init__(attrs=base)

    def render(self, name, value, attrs=None, renderer=None):
        # Use project TEMPLATES dirs (DjangoForms renderer would miss them).
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))
