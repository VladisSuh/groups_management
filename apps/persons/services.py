from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from .models import Person, PersonGroup, ChangeSet, PersonHistory
from typing import Optional, List, Dict, Any


class PersonService:
    """Сервис для работы с людьми и дедубликацией"""

    @staticmethod
    def create_change_set(author: str = None, reason: str = None) -> ChangeSet:
        """Создание нового набора изменений"""
        return ChangeSet.objects.create(author=author, reason=reason)

    @staticmethod
    def find_matching_group(person_data: Dict[str, Any]) -> Optional[int]:
        """Поиск подходящей группы для человека (бэкенд-реализация без SQL-функций).

        Условия (все должны выполняться):
        - Совпадение пола
        - Полное совпадение имён
        - Полное совпадение отчеств (оба NULL или равны)
        - Для мужчин — полное совпадение фамилий
        - Совпадение хотя бы одного контакта: address ИЛИ phone (если указан) ИЛИ email (если указан)
        Смотрим только по текущим записям.
        """
        qs = Person.objects.filter(
            is_current=True,
            gender=person_data['gender'],
            first_name=person_data['first_name'],
        )

        middle_name = person_data.get('middle_name')
        if middle_name is None:
            qs = qs.filter(middle_name__isnull=True)
        else:
            qs = qs.filter(middle_name=middle_name)

        if person_data['gender'] == 'М':
            qs = qs.filter(last_name=person_data['last_name'])

        contact_q = Q(address=person_data['address'])
        phone = person_data.get('phone')
        email = person_data.get('email')
        if phone:
            contact_q |= Q(phone=phone)
        if email:
            contact_q |= Q(email=email)

        group_id = (
            qs.filter(contact_q)
              .order_by('group_id')
              .values_list('group_id', flat=True)
              .first()
        )
        return int(group_id) if group_id is not None else None

    @staticmethod
    @transaction.atomic
    def create_person(person_data: Dict[str, Any], change_set: ChangeSet = None) -> Person:
        """Создание нового человека с дедубликацией"""
        if not change_set:
            change_set = PersonService.create_change_set(
                author='system',
                reason='API person creation'
            )

        # Поиск группы бэкендом
        group_id = PersonService.find_matching_group(person_data)
        if group_id:
            group = PersonGroup.objects.get(id=group_id)
        else:
            group = PersonGroup.objects.create()

        # Создание новой «текущей» версии человека
        now_ts = timezone.now()
        person = Person.objects.create(
            group=group,
            change=change_set,
            created_at=now_ts,
            is_current=True,
            **person_data
        )

        # Персистентность: закрыть предыдущую «текущую» запись в истории, если была
        prev = (
            Person.objects
            .filter(group=group, is_current=True)
            .exclude(id=person.id)
            .order_by('-created_at')
            .first()
        )
        if prev:
            PersonHistory.objects.create(
                group=group,
                change=person.change or prev.change,
                last_name=prev.last_name,
                first_name=prev.first_name,
                middle_name=prev.middle_name,
                birth_date=prev.birth_date,
                gender=prev.gender,
                address=prev.address,
                phone=prev.phone,
                email=prev.email,
                valid_from=prev.created_at,
                valid_to=now_ts,
            )

            # помечаем прошлую запись как неактуальную
            prev.is_current = False
            prev.save(update_fields=['is_current'])

        return person

    @staticmethod
    def search_persons_vitrine(search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Поиск в витрине (ORM, текущее состояние person)"""
        qs = Person.objects.filter(is_current=True)

        if search_params.get('last_name'):
            qs = qs.filter(last_name=search_params['last_name'])
        if search_params.get('first_name'):
            qs = qs.filter(first_name=search_params['first_name'])
        if search_params.get('middle_name') is not None and search_params.get('middle_name') != '':
            qs = qs.filter(middle_name=search_params['middle_name'])
        if search_params.get('address'):
            qs = qs.filter(address=search_params['address'])
        if search_params.get('phone'):
            qs = qs.filter(phone=search_params['phone'])
        if search_params.get('email'):
            qs = qs.filter(email=search_params['email'])

        limit = search_params.get('limit', 100)
        offset = search_params.get('offset', 0)

        qs = qs.order_by('group_id')[offset:offset + limit]

        return [
            {
                'group_id': p.group_id,
                'last_name': p.last_name,
                'first_name': p.first_name,
                'middle_name': p.middle_name,
                'birth_date': p.birth_date,
                'gender': p.gender,
                'address': p.address,
                'phone': p.phone,
                'email': p.email,
            }
            for p in qs
        ]

    @staticmethod
    def get_person_as_of(group_id: int, timestamp: timezone.datetime) -> Optional[Dict[str, Any]]:
        """Получение состояния человека на момент времени (ORM)."""
        # 1) пробуем взять текущую запись, созданную не позже timestamp
        current = (
            Person.objects
            .filter(group_id=group_id, is_current=True, created_at__lte=timestamp)
            .order_by('-created_at')
            .first()
        )
        if current:
            return {
                'group_id': current.group_id,
                'last_name': current.last_name,
                'first_name': current.first_name,
                'middle_name': current.middle_name,
                'birth_date': current.birth_date,
                'gender': current.gender,
                'address': current.address,
                'phone': current.phone,
                'email': current.email,
            }

        # 2) иначе ищем историческую запись, перекрывающую момент времени
        hist = (
            PersonHistory.objects
            .filter(group_id=group_id, valid_from__lte=timestamp, valid_to__gt=timestamp)
            .order_by('-valid_from')
            .first()
        )
        if hist:
            return {
                'group_id': hist.group_id,
                'last_name': hist.last_name,
                'first_name': hist.first_name,
                'middle_name': hist.middle_name,
                'birth_date': hist.birth_date,
                'gender': hist.gender,
                'address': hist.address,
                'phone': hist.phone,
                'email': hist.email,
            }
        return None

    @staticmethod
    def get_all_current_persons() -> List[Person]:
        """Получение всех текущих записей людей"""
        return Person.objects.filter(is_current=True).select_related('group', 'change')

    @staticmethod
    def get_person_history(group_id: int) -> List[PersonHistory]:
        """Получение истории изменений для группы"""
        return PersonHistory.objects.filter(group_id=group_id).order_by('valid_from')


class DatabaseInitService:
    """Сервис для инициализации базы данных"""

    @staticmethod
    def execute_sql_script(sql_content: str):
        """Выполнение SQL скрипта"""
        with connection.cursor() as cursor:
            # Разбиваем скрипт на отдельные команды
            statements = sql_content.split(';')
            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    try:
                        cursor.execute(statement)
                    except Exception as e:
                        print(f"Error executing statement: {statement[:100]}...")
                        print(f"Error: {e}")
                        raise

    @staticmethod
    def load_sql_script_from_file(file_path: str):
        """Загрузка и выполнение SQL скрипта из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                sql_content = file.read()
                DatabaseInitService.execute_sql_script(sql_content)
                print(f"SQL script from {file_path} executed successfully")
        except Exception as e:
            print(f"Error loading SQL script: {e}")
            raise
