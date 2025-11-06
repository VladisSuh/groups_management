from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from datetime import datetime
import json
from .persistency_service import PersistencyService
from .models import Person, PersonGroup


@method_decorator(csrf_exempt, name='dispatch')
class PersistencyAPIView(View):
    """
    Base view for persistency API endpoints.
    """
    
    def dispatch(self, request, *args, **kwargs):
        """
        Handle CORS and common response formatting.
        """
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(response, 'headers'):
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    def options(self, request, *args, **kwargs):
        """
        Handle CORS preflight requests.
        """
        response = JsonResponse({})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response


class GroupHistoryView(PersistencyAPIView):
    """
    API endpoint for getting group history.
    GET /api/persistency/groups/<group_name>/history/
    """
    
    def get(self, request, group_name):
        try:
            limit = request.GET.get('limit')
            if limit:
                limit = int(limit)
            
            history = PersistencyService.get_group_history(group_name, limit=limit)
            
            return JsonResponse({
                'success': True,
                'group_name': group_name,
                'history': history
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class GroupAtTimeView(PersistencyAPIView):
    """
    API endpoint for getting group composition at a specific time.
    GET /api/persistency/groups/<group_name>/at-time/?timestamp=<iso_timestamp>
    """
    
    def get(self, request, group_name):
        try:
            timestamp_str = request.GET.get('timestamp')
            if not timestamp_str:
                return JsonResponse({
                    'success': False,
                    'error': 'timestamp parameter is required'
                }, status=400)
            
            # Parse ISO timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            members = PersistencyService.get_group_at_time(group_name, timestamp)
            
            if members is None:
                return JsonResponse({
                    'success': False,
                    'error': f'Group {group_name} not found'
                }, status=404)
            
            # Convert Person objects to JSON
            members_data = [
                {
                    'id': person.id,
                    'full_name': person.full_name,
                    'phone': person.phone,
                    'email': person.email,
                    'address': person.address
                }
                for person in members
            ]
            
            return JsonResponse({
                'success': True,
                'group_name': group_name,
                'timestamp': timestamp_str,
                'members': members_data,
                'member_count': len(members_data)
            })
            
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid timestamp format: {str(e)}'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class ChangesetListView(PersistencyAPIView):
    """
    API endpoint for getting all changesets.
    GET /api/persistency/changesets/
    """
    
    def get(self, request):
        try:
            limit = request.GET.get('limit')
            if limit:
                limit = int(limit)
            
            changesets = PersistencyService.get_all_changesets(limit=limit)
            
            return JsonResponse({
                'success': True,
                'changesets': changesets
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class ChangesetDetailView(PersistencyAPIView):
    """
    API endpoint for getting changeset details.
    GET /api/persistency/changesets/<changeset_id>/
    """
    
    def get(self, request, changeset_id):
        try:
            details = PersistencyService.get_changeset_details(changeset_id)
            
            if details is None:
                return JsonResponse({
                    'success': False,
                    'error': f'Changeset {changeset_id} not found'
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'details': details
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class GroupManagementView(PersistencyAPIView):
    """
    API endpoint for managing group membership.
    POST /api/persistency/groups/<group_name>/members/
    DELETE /api/persistency/groups/<group_name>/members/<person_id>/
    """
    
    def post(self, request, group_name):
        """
        Add a person to a group.
        """
        try:
            data = json.loads(request.body)
            person_id = data.get('person_id')
            description = data.get('description', '')
            author = data.get('author', 'API User')
            
            if not person_id:
                return JsonResponse({
                    'success': False,
                    'error': 'person_id is required'
                }, status=400)
            
            try:
                person = Person.objects.get(id=person_id)
            except Person.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Person {person_id} not found'
                }, status=404)
            
            changeset = PersistencyService.create_changeset(
                description=description,
                author=author
            )
            
            PersistencyService.add_person_to_group(
                group_name=group_name,
                person=person,
                changeset=changeset,
                description=description
            )
            
            return JsonResponse({
                'success': True,
                'changeset_id': changeset.id,
                'message': f'Added {person.full_name} to group {group_name}'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def delete(self, request, group_name, person_id):
        """
        Remove a person from a group.
        """
        try:
            # Parse query parameters for optional data
            description = request.GET.get('description', '')
            author = request.GET.get('author', 'API User')
            
            try:
                person = Person.objects.get(id=person_id)
            except Person.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Person {person_id} not found'
                }, status=404)
            
            changeset = PersistencyService.create_changeset(
                description=description,
                author=author
            )
            
            PersistencyService.remove_person_from_group(
                group_name=group_name,
                person=person,
                changeset=changeset,
                description=description
            )
            
            return JsonResponse({
                'success': True,
                'changeset_id': changeset.id,
                'message': f'Removed {person.full_name} from group {group_name}'
            })
            
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class CompareGroupStatesView(PersistencyAPIView):
    """
    API endpoint for comparing group states between two timestamps.
    GET /api/persistency/groups/<group_name>/compare/?timestamp1=<iso>&timestamp2=<iso>
    """
    
    def get(self, request, group_name):
        try:
            timestamp1_str = request.GET.get('timestamp1')
            timestamp2_str = request.GET.get('timestamp2')
            
            if not timestamp1_str or not timestamp2_str:
                return JsonResponse({
                    'success': False,
                    'error': 'Both timestamp1 and timestamp2 parameters are required'
                }, status=400)
            
            # Parse timestamps
            timestamp1 = datetime.fromisoformat(timestamp1_str.replace('Z', '+00:00'))
            timestamp2 = datetime.fromisoformat(timestamp2_str.replace('Z', '+00:00'))
            
            comparison = PersistencyService.compare_group_states(
                group_name, timestamp1, timestamp2
            )
            
            return JsonResponse({
                'success': True,
                'group_name': group_name,
                'timestamp1': timestamp1_str,
                'timestamp2': timestamp2_str,
                'comparison': comparison
            })
            
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid timestamp format: {str(e)}'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class PersonHistoryView(PersistencyAPIView):
    """
    API endpoint for getting person's group membership history.
    GET /api/persistency/persons/<person_id>/history/
    """
    
    def get(self, request, person_id):
        try:
            history = PersistencyService.get_person_group_history(person_id)
            
            return JsonResponse({
                'success': True,
                'person_id': person_id,
                'history': history
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class GroupHistoryByIdView(PersistencyAPIView):
    """
    API endpoint for getting group history by ID.
    GET /api/groups/<group_id>/history/
    """
    
    def get(self, request, group_id):
        try:
            limit = request.GET.get('limit')
            if limit:
                limit = int(limit)
            
            history = PersistencyService.get_group_history(group_id, limit=limit)
            
            return JsonResponse({
                'success': True,
                'group_id': group_id,
                'history': history
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class GroupAtTimeByIdView(PersistencyAPIView):
    """
    API endpoint for getting group composition at a specific time by ID.
    GET /api/groups/<group_id>/at-time/?timestamp=<iso_timestamp>
    """
    
    def get(self, request, group_id):
        try:
            timestamp_str = request.GET.get('timestamp')
            if not timestamp_str:
                return JsonResponse({
                    'success': False,
                    'error': 'timestamp parameter is required'
                }, status=400)
            
            # Parse ISO timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            members = PersistencyService.get_group_at_time(group_id, timestamp)
            
            if members is None:
                return JsonResponse({
                    'success': False,
                    'error': f'Group {group_id} not found'
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'group_id': group_id,
                'timestamp': timestamp_str,
                'members': members,
                'member_count': len(members)
            })
            
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid timestamp format: {str(e)}'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


# Function-based views for simpler endpoints
@csrf_exempt
@require_http_methods(["GET"])
def get_groups_list(request):
    """
    Get list of all groups.
    GET /api/persistency/groups/
    """
    try:
        # Получаем все группы с подсчетом участников
        groups = PersonGroup.objects.all()
        groups_list = []
        
        for group in groups:
            # Подсчитываем всех участников группы (все записи актуальны)
            member_count = Person.objects.filter(group=group).count()
            
            # Получаем последнее изменение в группе
            latest_person = Person.objects.filter(group=group).order_by('-created_at').first()
            
            groups_list.append({
                'id': group.id,
                'name': str(group.id),  # Просто номер группы
                'created_at': latest_person.created_at.isoformat() if latest_person else None,
                'description': f"{member_count} участников",
                'member_count': member_count
            })
        
        return JsonResponse({
            'success': True,
            'groups': groups_list
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
