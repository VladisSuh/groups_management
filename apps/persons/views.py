from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from .models import Person
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


def index_view(request):
    """Главная страница"""
    return render(request, 'persons/index.html')


def list_persons_view(request):
    """Страница со списком людей и поиском в витрине"""
    try:
        persons = PersonService.get_all_current_persons()
        return render(request, 'persons/list_persons.html', {'persons': persons})
    except Exception as e:
        return render(request, 'persons/error.html', {'error': str(e)})
