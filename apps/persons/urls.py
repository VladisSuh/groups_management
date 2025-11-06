from django.urls import path
from . import views
from . import persistency_views

urlpatterns = [
    # Веб-страницы
    path('', views.index_view, name='index'),
    path('create/', views.PersonCreateView.as_view(), name='create_person'),
    path('list/', views.list_persons_view, name='list_persons'),  # Совмещенная страница списка и поиска
    
    # API endpoints для работы с людьми
    path('api/persons/', views.api_create_person, name='api_create_person'),
    path('api/persons/create/', views.api_create_person, name='api_create_person_legacy'),
    path('api/persons/list/', views.api_list_persons, name='api_list_persons'),
    path('api/persons/search/', views.api_search_persons, name='api_search_persons'),
    path('api/persons/<int:group_id>/as-of/', views.api_person_as_of, name='api_person_as_of'),
    
    # API endpoints для истории групп (простые по ID)
    path('api/groups/<int:group_id>/history/', views.api_group_history_simple, name='api_group_history_simple'),
    path('api/groups/<int:group_id>/at-time/', views.api_group_at_time, name='api_group_at_time'),
    
    # API endpoints для работы с адресами (DaData)
    path('api/address/suggestions/', views.api_address_suggestions, name='api_address_suggestions'),
    path('api/address/clean/', views.api_clean_address, name='api_clean_address'),
    path('api/address/geocode/', views.api_geocode_address, name='api_geocode_address'),
    
    # API endpoints для персистентности (Git-like versioning)
    path('api/persistency/groups/', persistency_views.get_groups_list, name='api_persistency_groups_list'),
    
    # API endpoints для персистентности по ID группы (должны быть ПЕРЕД endpoints с именами)
    path('api/persistency/groups/<int:group_id>/history/', persistency_views.GroupHistoryByIdView.as_view(), name='api_group_history_by_id'),
    path('api/persistency/groups/<int:group_id>/at-time/', persistency_views.GroupAtTimeByIdView.as_view(), name='api_group_at_time_by_id'),
    
    # API endpoints для персистентности по имени группы
    path('api/persistency/groups/<str:group_name>/history/', persistency_views.GroupHistoryView.as_view(), name='api_group_history'),
    path('api/persistency/groups/<str:group_name>/at-time/', persistency_views.GroupAtTimeView.as_view(), name='api_group_at_time'),
    path('api/persistency/groups/<str:group_name>/compare/', persistency_views.CompareGroupStatesView.as_view(), name='api_compare_group_states'),
    path('api/persistency/groups/<str:group_name>/members/', persistency_views.GroupManagementView.as_view(), name='api_group_members'),
    path('api/persistency/groups/<str:group_name>/members/<int:person_id>/', persistency_views.GroupManagementView.as_view(), name='api_group_member_delete'),
    
    path('api/persistency/changesets/', persistency_views.ChangesetListView.as_view(), name='api_changesets_list'),
    path('api/persistency/changesets/<uuid:changeset_id>/', persistency_views.ChangesetDetailView.as_view(), name='api_changeset_detail'),
    path('api/persistency/persons/<int:person_id>/history/', persistency_views.PersonHistoryView.as_view(), name='api_person_history'),
]
