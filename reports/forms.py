


from django import forms
from .models import Report
from django.contrib.auth import get_user_model

class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'file']


class ProfilForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['nom', 'prenom', 'filiale', 'email']
        labels = {
            'nom': 'Nom',
            'prenom': 'Prénom',
            'filiale': 'Filiale',
            'email': 'Adresse mail',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
            'filiale': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

