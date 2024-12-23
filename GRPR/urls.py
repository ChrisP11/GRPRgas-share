from django.urls import path
from GRPR import views

urlpatterns = [
    path('', views.home_page, name='home_page'),
    path('tee_sheet', views.teesheet_view, name='teesheet_view'),
    path('schedule', views.schedule_view, name='schedule_view'),
    path('subswap', views.subswap_view, name='subswap_view'), 
    path('subrequest', views.subrequest_view, name='subrequest_view'),
    path('subrequestsent', views.subrequestsent_view, name='subrequestsent_view'),
    path('swaprequest', views.swaprequest_view, name='swaprequest_view'),
    path('swaprequestsent', views.swaprequestsent_view, name='swaprequestsent_view'),
    path('swapoffer/', views.swapoffer_view, name='swapoffer_view'), 
    path('swapcounter/', views.swapcounter_view, name='swapcounter_view'), 
    path('swapcounteraccept/', views.swapcounteraccept_view, name='swapcounteraccept_view'), 
]
