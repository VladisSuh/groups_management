from django.urls import path
from . import views

urlpatterns = [
    # Веб-страницы
    path('', views.index_view, name='index'),
    path('create/', views.PersonCreateView.as_view(), name='create_person'),
    path('list/', views.list_persons_view, name='list_persons'),
    
    # API endpoints
    path('api/persons/', views.api_create_person, name='api_create_person'),
    path('api/persons/create/', views.api_create_person, name='api_create_person_legacy'),
    path('api/persons/list/', views.api_list_persons, name='api_list_persons'),
    path('api/persons/search/', views.api_search_persons, name='api_search_persons'),
    path('api/persons/<int:group_id>/as-of/', views.api_person_as_of, name='api_person_as_of'),
]
