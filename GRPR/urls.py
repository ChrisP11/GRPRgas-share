from django.urls import path
from GRPR import views
from django.contrib.auth import views as auth_views
from GRPR.views import CustomLoginView, register, CustomPasswordChangeView
# from .views import admin_view

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('register/', register, name='register'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', CustomLoginView.as_view(), name='login'),  # Set the root URL to the login view
    path('home/', views.home_page, name='home_page'),  
    path('tee_sheet/', views.teesheet_view, name='teesheet_view'),
    path('schedule/', views.schedule_view, name='schedule_view'),
    path('subswap/', views.subswap_view, name='subswap_view'), 
    path('store_sub_request_data/', views.store_sub_request_data_view, name='store_sub_request_data_view'), 
    path('subrequest/', views.subrequest_view, name='subrequest_view'),
    path('store_sub_request_sent_data/', views.store_sub_request_sent_data_view, name='store_sub_request_sent_data_view'),
    path('subrequestsent/', views.subrequestsent_view, name='subrequestsent_view'),
    path('store_subaccept_data/', views.store_subaccept_data_view, name='store_subaccept_data_view'),
    path('subaccept/', views.subaccept_view, name='subaccept_view'),
    path('store_subfinal_data/', views.store_subfinal_data_view, name='store_subfinal_data_view'),
    path('subfinal/', views.subfinal_view, name='subfinal_view'),
    path('store_subcancelconfirm_data/', views.store_subcancelconfirm_data_view, name='store_subcancelconfirm_data_view'),
    path('subcancelconfirm/', views.subcancelconfirm_view, name='subcancelconfirm_view'),
    path('store_subcancel_data/', views.store_subcancel_data_view, name='store_subcancel_data_view'),
    path('subcancel/', views.subcancel_view, name='subcancel_view'),
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
    path('statistics/', views.statistics_view, name='statistics_view'),
    path('players/', views.players_view, name='players_view'),
    path('profile/', views.profile_view, name='profile_view'),
    path('password_change/', CustomPasswordChangeView.as_view(), name='password_change'),  
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='GRPR/password_change_done.html'), name='password_change_done'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='GRPR/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='GRPR/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='GRPR/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='GRPR/password_reset_complete.html'), name='password_reset_complete'),
    path('admin_page/', views.admin_view, name='admin_page'),
    path('send-test-email/', views.send_test_email, name='send_test_email'),
    

]
