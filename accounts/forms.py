from django import forms
from django.contrib.auth.forms import AuthenticationForm

class TailwindFormMixin:
    """Mixin to apply DaisyUI/Tailwind classes to form fields"""
    INPUT_CLS = "input input-bordered w-full"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.EmailInput, forms.PasswordInput)):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.INPUT_CLS}'.strip()
            
            # Set sensible autocomplete
            if isinstance(widget, forms.EmailInput):
                widget.attrs.setdefault("autocomplete", "email")
            if isinstance(widget, forms.PasswordInput):
                widget.attrs.setdefault("autocomplete", "current-password")


class LoginForm(TailwindFormMixin, AuthenticationForm):
    """Login form with Tailwind styling"""
    pass