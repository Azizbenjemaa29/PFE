from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import Report
from django.contrib.auth import get_user_model


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'file']


class ProfilForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['nom', 'prenom', 'filiale', 'email', 'avatar']
        labels = {
            'nom': 'Nom',
            'prenom': 'Prénom',
            'filiale': 'Filiale',
            'email': 'Adresse mail',
            'avatar': 'Photo de profil',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
            'filiale': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class AdminChangePasswordForm(forms.Form):
    password1 = forms.CharField(
        label='Nouveau mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=8,
    )
    password2 = forms.CharField(
        label='Confirmer le mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Les mots de passe ne correspondent pas.')
        if p1:
            validate_password(p1)
        return cleaned_data
