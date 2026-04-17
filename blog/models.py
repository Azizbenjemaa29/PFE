from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('user', 'User'),
]

class CustomUserManager(BaseUserManager):
    def create_user(self, nom, prenom, filiale, password=None, role='user'):
        if not nom:
            raise ValueError("Le nom est obligatoire")
        user = self.model(
            nom=nom,
            prenom=prenom,
            filiale=filiale,
            role=role,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, nom, prenom, filiale, password):
        user = self.create_user(
            nom=nom,
            prenom=prenom,
            filiale=filiale,
            password=password,
            role='admin',
        )
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class CustomUser(AbstractBaseUser, PermissionsMixin):
    nom = models.CharField(max_length=100, unique=True)
    prenom = models.CharField(max_length=100)
    filiale = models.CharField(max_length=100)
    email = models.EmailField(max_length=254, blank=True, default='')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = "nom"
    REQUIRED_FIELDS = ["prenom", "filiale"]

    def __str__(self):
        return f"{self.nom} ({self.role})"

    def get_full_name(self):
        return f"{self.nom} {self.prenom}"

    def get_short_name(self):
        return self.nom

    @property
    def username(self):
        return self.nom

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_user(self):
        return self.role == 'user'