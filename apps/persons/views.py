from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from .models import Person, PersonHistory, ChangeSet
from .serializers import PersonSerializer, PersonSearchSerializer, PersonVitrineSerializer
from .services import PersonService


@method_decorator(csrf_exempt, name='dispatch')
class PersonCreateView(View):
    """Простая веб-страница для добавления людей"""
    
    def get(self, request):
        """Отображение формы"""
        return render(request, 'persons/create_person.html')
    
    def post(self, request):
        """Обработка создания человека"""
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
            
            serializer = PersonSerializer(data=data)
            if serializer.is_valid():
                person = PersonService.create_person(serializer.validated_data)
                return JsonResponse({
                    'success': True,
                    'message': 'Человек успешно добавлен',
                    'person_id': person.id,
                    'group_id': person.group.id
                })
            else:
                return JsonResponse({
                    'success': False,
                    'errors': serializer.errors
                }, status=400)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@api_view(['POST'])
def api_create_person(request):
    """API endpoint для создания человека"""
    serializer = PersonSerializer(data=request.data)
    if serializer.is_valid():
        try:
            person = PersonService.create_person(serializer.validated_data)
            return Response({
                'success': True,
                'message': 'Человек успешно добавлен',
                'person_id': person.id,
                'group_id': person.group.id if person.group else None,
                'data': PersonSerializer(person).data
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def api_search_persons(request):
    """API endpoint для поиска людей в витрине"""
    search_serializer = PersonSearchSerializer(data=request.query_params)
    
    if search_serializer.is_valid():
        try:
            results = PersonService.search_persons_vitrine(search_serializer.validated_data)
            vitrine_serializer = PersonVitrineSerializer(results, many=True)
            
            return Response({
                'success': True,
                'count': len(results),
                'data': vitrine_serializer.data
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({
        'success': False,
        'errors': search_serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def api_list_persons(request):
    """API endpoint для получения списка всех текущих людей"""
    try:
        persons = PersonService.get_all_current_persons()
        serializer = PersonSerializer(persons, many=True)
        
        return Response({
            'success': True,
            'count': len(persons),
            'data': serializer.data
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def api_person_as_of(request, group_id):
    """API endpoint для получения состояния человека на определенный момент времени"""
    timestamp_str = request.query_params.get('timestamp')
    
    if not timestamp_str:
        return Response({
            'success': False,
            'error': 'Timestamp parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        from datetime import datetime
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        
        result = PersonService.get_person_as_of(group_id, timestamp)
        
        if result:
            return Response({
                'success': True,
                'data': result
            })
        else:
            return Response({
                'success': False,
                'error': 'Person not found for the specified timestamp'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except ValueError as e:
        return Response({
            'success': False,
            'error': f'Invalid timestamp format: {e}'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
def api_group_history_simple(request, group_id):
    """Получить историю изменений группы в простом формате"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET method allowed'}, status=405)
    
    try:
        # Получаем историю изменений для группы
        history = PersonHistory.objects.filter(
            group_id=group_id
        ).select_related('change').order_by('-valid_from')
        
        result = []
        
        # Всегда добавляем текущее состояние группы
        current_members = Person.objects.filter(group_id=group_id)
        current_member_names = set()
        
        for member in current_members:
            # Формируем полное имя для текущего члена
            member_name_parts = [member.last_name, member.first_name]
            if member.middle_name:
                member_name_parts.append(member.middle_name)
            member_full_name = " ".join(member_name_parts)
            current_member_names.add(member_full_name)
            
            # Добавляем текущего члена как "действующую" запись
            from django.utils import timezone
            result.append({
                'timestamp': member.change.authored_at.isoformat() if member.change else timezone.now().isoformat(),
                'author': member.change.author if member.change else 'system',
                'reason': 'Текущий член группы',
                'name': member_full_name,
                'valid_from': member.change.authored_at.isoformat() if member.change else timezone.now().isoformat(),
                'valid_to': 'текущее время',
                'is_current': True  # Флаг для отличия от исторических записей
            })
        
        # Добавляем исторические записи только для людей, которых нет в текущем составе
        for record in history:
            # Формируем полное имя из компонентов
            name_parts = [record.last_name, record.first_name]
            if record.middle_name:
                name_parts.append(record.middle_name)
            full_name = " ".join(name_parts)
            
            # Добавляем только если этого человека нет в текущем составе
            if full_name not in current_member_names:
                result.append({
                    'timestamp': record.change.authored_at.isoformat() if record.change else record.valid_from.isoformat(),
                    'author': record.change.author if record.change else 'System',
                    'reason': record.change.reason if record.change else 'History record',
                    'name': full_name,
                    'valid_from': record.valid_from.isoformat(),
                    'valid_to': record.valid_to.isoformat()
                })

        # Сортируем результат по времени (новые сначала)
        result.sort(key=lambda x: x['timestamp'], reverse=True)

        return JsonResponse({
            'status': 'success',
            'history': result
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_group_at_time(request, group_id):
    """Получить состояние группы на определенный момент времени"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET method allowed'}, status=405)
    
    try:
        timestamp_str = request.GET.get('timestamp')
        if not timestamp_str:
            return JsonResponse({'error': 'timestamp parameter is required'}, status=400)
        
        # Parse ISO timestamp
        from datetime import datetime
        from django.utils import timezone as django_timezone
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        
        # Сначала ищем в истории
        history_record = PersonHistory.objects.select_related('change').filter(
            group_id=group_id,
            valid_from__lte=timestamp,
            valid_to__gt=timestamp
        ).first()
        
        if history_record:
            # Найдена историческая запись
            result = {
                'group_id': group_id,
                'timestamp': timestamp_str,
                'person': {
                    'last_name': history_record.last_name,
                    'first_name': history_record.first_name,
                    'middle_name': history_record.middle_name,
                    'birth_date': history_record.birth_date.isoformat() if history_record.birth_date else None,
                    'gender': history_record.gender,
                    'address': history_record.address,
                    'phone': history_record.phone,
                    'email': history_record.email,
                    'created_at': history_record.valid_from.isoformat() if history_record.valid_from else None
                },
                'change_info': {
                    'timestamp': history_record.change.authored_at.isoformat() if history_record.change else None,
                    'author': history_record.change.author if history_record.change else None,
                    'reason': history_record.change.reason if history_record.change else None
                } if history_record.change else None
            }
            
            return JsonResponse({
                'status': 'success',
                'data': result
            })
        else:
            # Не найдено в истории, ищем в текущих записях
            current_persons = Person.objects.filter(group_id=group_id)
            if current_persons.exists():
                # Возвращаем всех текущих участников группы
                members = []
                for person in current_persons:
                    members.append({
                        'last_name': person.last_name,
                        'first_name': person.first_name,
                        'middle_name': person.middle_name,
                        'birth_date': person.birth_date.isoformat() if person.birth_date else None,
                        'gender': person.gender,
                        'address': person.address,
                        'phone': person.phone,
                        'email': person.email,
                        'created_at': person.created_at.isoformat() if person.created_at else None
                    })
                
                return JsonResponse({
                    'status': 'success',
                    'group_id': group_id,
                    'timestamp': timestamp_str,
                    'members': members,
                    'is_current': True
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'error': 'No data found for specified timestamp'
                }, status=404)
            
    except ValueError as e:
        return JsonResponse({'error': f'Invalid timestamp format: {e}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_address_suggestions(request):
    """API endpoint для получения подсказок адресов (заглушка)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        return JsonResponse({
            'success': True,
            'suggestions': []  # Заглушка - пока не реализовано
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_clean_address(request):
    """API endpoint для очистки адреса (заглушка)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        return JsonResponse({
            'success': True,
            'result': None  # Заглушка - пока не реализовано
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_geocode_address(request):
    """API endpoint для геокодирования адреса (заглушка)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        return JsonResponse({
            'success': True,
            'result': None  # Заглушка - пока не реализовано
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def index_view(request):
    """Главная страница"""
    return render(request, 'persons/index.html')


def list_persons_view(request):
    """Страница со списком людей"""
    try:
        persons = PersonService.get_all_current_persons()
        return render(request, 'persons/list_persons.html', {'persons': persons})
    except Exception as e:
        return render(request, 'persons/error.html', {'error': str(e)})
