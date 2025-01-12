from django.urls import path
from GRPR import views
from django.contrib.auth import views as auth_views
from GRPR.views import CustomLoginView, register

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('register/', register, name='register'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', CustomLoginView.as_view(), name='login'),  # Set the root URL to the login view
    path('home/', views.home_page, name='home_page'),  
    path('tee_sheet/', views.teesheet_view, name='teesheet_view'),
    path('schedule/', views.schedule_view, name='schedule_view'),
    path('subswap/', views.subswap_view, name='subswap_view'), 
    path('subrequest/', views.subrequest_view, name='subrequest_view'),
    path('subrequestsent/', views.subrequestsent_view, name='subrequestsent_view'),
    path('store_swap_data/', views.store_swap_data_view, name='store_swap_data_view'),
    path('swaprequest/', views.swaprequest_view, name='swaprequest_view'),
    path('store_swaprequestsent_data/', views.store_swaprequestsent_data_view, name='store_swaprequestsent_data_view'),
    path('swaprequestsent/', views.swaprequestsent_view, name='swaprequestsent_view'),
    path('store_swapoffer_data/', views.store_swapoffer_data_view, name='store_swapoffer_data_view'),
    path('swapoffer/', views.swapoffer_view, name='swapoffer_view'), 
    path('store_swapcounter_data/', views.store_swapcounter_data_view, name='store_swapcounter_data_view'),
    path('swapcounter/', views.swapcounter_view, name='swapcounter_view'), 
    path('store_swapcounteraccept_data/', views.store_swapcounteraccept_data_view, name='store_swapcounteraccept_data_view'),
    path('swapcounteraccept/', views.swapcounteraccept_view, name='swapcounteraccept_view'), 
    path('store_swapfinal_data/', views.store_swapfinal_data_view, name='store_swapfinal_data_view'),
    path('swapfinal/', views.swapfinal_view, name='swapfinal_view'),
    path('store_swapcancelconfirm_data/', views.store_swapcancelconfirm_data_view, name='store_swapcancelconfirm_data_view'),
    path('swapcancelconfirm/', views.swapcancelconfirm_view, name='swapcancelconfirm_view'),
    path('store_swapcancel_data/', views.store_swapcancel_data_view, name='store_swapcancel_data_view'),
    path('swapcancel/', views.swapcancel_view, name='swapcancel_view'),
    path('swapnoneavail/', views.swapnoneavail_view, name='swapnoneavail_view'),
]
