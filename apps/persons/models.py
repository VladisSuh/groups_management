from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
import re


class ChangeSet(models.Model):
    """Таблица изменений (коммитов)"""
    id = models.BigAutoField(primary_key=True)
    authored_at = models.DateTimeField(default=timezone.now)
    author = models.TextField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'change_set'
        managed = False  # Django не будет управлять этой таблицей

    def __str__(self):
        return f"ChangeSet {self.id} by {self.author or 'Unknown'}"


class PersonGroup(models.Model):
    """Группа людей (дедубликация)"""
    id = models.AutoField(primary_key=True)

    class Meta:
        db_table = 'person_group'
        managed = False  # Django не будет управлять этой таблицей

    def __str__(self):
        return f"Group {self.id}"


class Person(models.Model):
    """Основная таблица людей с персистентностью"""
    GENDER_CHOICES = [
        ('М', 'Мужской'),
        ('Ж', 'Женский'),
    ]

    id = models.AutoField(primary_key=True)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE, null=True, blank=True)
    change = models.ForeignKey(ChangeSet, on_delete=models.SET_NULL, null=True, blank=True)
    
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    birth_date = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    address = models.TextField()
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'person'
        managed = False  # Django не будет управлять этой таблицей
        indexes = [
            models.Index(fields=['is_current'], name='i_person_current'),
            models.Index(fields=['group'], name='i_person_group'),
            models.Index(fields=['phone'], name='i_person_phone'),
            models.Index(fields=['email'], name='i_person_email'),
        ]

    def clean(self):
        """Валидация полей"""
        errors = {}
        
        # Валидация фамилии
        if not self._validate_name(self.last_name):
            errors['last_name'] = 'Фамилия должна начинаться с большой буквы, содержать минимум 2 символа кириллицы и дефис'
            
        # Валидация имени
        if not self._validate_name(self.first_name):
            errors['first_name'] = 'Имя должно начинаться с большой буквы, содержать минимум 2 символа кириллицы и дефис'
            
        # Валидация отчества (если указано)
        if self.middle_name and not self._validate_name(self.middle_name):
            errors['middle_name'] = 'Отчество должно начинаться с большой буквы, содержать минимум 2 символа кириллицы и дефис'
            
        # Валидация телефона (если указан)
        if self.phone and not self._validate_phone(self.phone):
            errors['phone'] = 'Телефон должен быть в формате +7(XXX)XXX-XX-XX, где X - любая цифра'
            
        # Валидация email (если указан)
        if self.email and not self._validate_email(self.email):
            errors['email'] = 'Email должен быть в формате login@domain, где login и domain минимум 3 символа'
            
        # Валидация адреса
        if not self.address or not self.address.strip():
            errors['address'] = 'Адрес не может быть пустым'
            
        if errors:
            raise ValidationError(errors)

    def _validate_name(self, name):
        """Валидация имени/фамилии/отчества"""
        if not name or len(name) < 2:
            return False
        return bool(re.match(r'^[А-ЯЁ][а-яё-]{1,}$', name))

    def _validate_phone(self, phone):
        """Валидация и нормализация телефона в формат +7(XXX)XXX-XX-XX"""
        if not phone:
            return True
        
        # Убираем все символы кроме цифр
        digits_only = re.sub(r'[^\d]', '', phone.strip())
        
        # Если номер начинается с 8, заменяем на 7
        if digits_only.startswith('8') and len(digits_only) == 11:
            digits_only = '7' + digits_only[1:]
        
        # Проверяем, что у нас российский номер (11 цифр, начинается с 7)
        if len(digits_only) == 11 and digits_only.startswith('7'):
            # Форматируем в +7(XXX)XXX-XX-XX
            formatted_phone = f"+7({digits_only[1:4]}){digits_only[4:7]}-{digits_only[7:9]}-{digits_only[9:11]}"
            # Сохраняем отформатированный номер обратно в объект
            self.phone = formatted_phone
            return True
        
        # Если не удалось преобразовать, возвращаем False
        return False

    def _validate_email(self, email):
        """Валидация email"""
        pattern = r'^[A-Za-z0-9]{3,}([._][A-Za-z0-9]+)*@[A-Za-z0-9]{3,}([.-][A-Za-z0-9]+)*$'
        return bool(re.match(pattern, email))

        

    def __str__(self):
        return f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()


class PersonHistory(models.Model):
    """История изменений людей"""
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(PersonGroup, on_delete=models.CASCADE)
    change = models.ForeignKey(ChangeSet, on_delete=models.SET_NULL, null=True, blank=True)
    
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    birth_date = models.DateField()
    gender = models.CharField(max_length=1, choices=Person.GENDER_CHOICES)
    address = models.TextField()
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    class Meta:
        db_table = 'person_history'
        managed = False  # Django не будет управлять этой таблицей
        indexes = [
            models.Index(fields=['group', 'valid_from', 'valid_to'], name='i_hist_group_from_to'),
        ]

    def __str__(self):
        return f"History: {self.last_name} {self.first_name} ({self.valid_from} - {self.valid_to})"
