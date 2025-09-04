from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm as DjangoPasswordResetForm,
    SetPasswordForm as DjangoSetPasswordForm,
    PasswordChangeForm as DjangoPasswordChangeForm,
    UserCreationForm as DjangoUserCreationForm,
)

class TailwindFormMixin:
    INPUT_CLS = "input input-bordered w-full"
    TEXTAREA_CLS = "textarea textarea-bordered w-full"
    SELECT_CLS = "select select-bordered w-full"
    CHECKBOX_CLS = "checkbox"
    FILE_CLS = "file-input file-input-bordered w-full"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            # text-ish
            if isinstance(widget, (forms.TextInput, forms.EmailInput, forms.URLInput,
                                   forms.PasswordInput, forms.NumberInput, forms.DateInput,
                                   forms.DateTimeInput, forms.TimeInput)):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.INPUT_CLS}'.strip()
            # textarea
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.TEXTAREA_CLS}'.strip()
            # select
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.SELECT_CLS}'.strip()
            # checkbox / file
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.CHECKBOX_CLS}'.strip()
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = f'{widget.attrs.get("class","")} {self.FILE_CLS}'.strip()

            # sensible autocomplete defaults
            if isinstance(widget, forms.EmailInput):
                widget.attrs.setdefault("autocomplete", "email")
            if isinstance(widget, forms.PasswordInput):
                # Django sets autocomplete on some password fields already; leave if present.
                widget.attrs.setdefault("autocomplete", "current-password")

class LoginForm(TailwindFormMixin, AuthenticationForm):
    pass

class PasswordResetForm(TailwindFormMixin, DjangoPasswordResetForm):
    pass

class SetPasswordForm(TailwindFormMixin, DjangoSetPasswordForm):
    pass

class PasswordChangeForm(TailwindFormMixin, DjangoPasswordChangeForm):
    pass

class SignupForm(TailwindFormMixin, DjangoUserCreationForm):
    pass
