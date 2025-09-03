from django.urls import path
from GRPR import views
from django.contrib.auth import views as auth_views
from GRPR.views import CustomLoginView, register, CustomPasswordChangeView, sms_reply
# from .views import sms_reply
# from .views import admin_view

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('register/', register, name='register'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', CustomLoginView.as_view(), name='login'),  # Set the root URL to the login view
    path('home/', views.home_page, name='home_page'),  
    path('about/', views.about_view, name='about'),
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
    path('store_swaprequestsent_data/', views.store_swap_request_sent_data_view, name='store_swap_request_sent_data_view'),
    path('swaprequestsent/', views.swaprequestsent_view, name='swaprequestsent_view'),
    path('store_swapoffer_data/', views.store_swapoffer_data_view, name='store_swapoffer_data_view'),
    path('swapoffer/', views.swapoffer_view, name='swapoffer_view'), 
    path('store_swapcounter_data/', views.store_swapcounter_data_view, name='store_swapcounter_data_view'),
    path('swapcounter/', views.swapcounter_view, name='swapcounter_view'), 
    path('store_swapcounteraccept_data/', views.store_swapcounteraccept_data_view, name='store_swapcounteraccept_data_view'),
    path('swapcounteraccept/', views.swapcounteraccept_view, name='swapcounteraccept_view'), 
    path('swapcounterreject/', views.swapcounterreject_view, name='swapcounterreject_view'),
    path('store_swapfinal_data/', views.store_swapfinal_data_view, name='store_swapfinal_data_view'),
    path('swapfinal/', views.swapfinal_view, name='swapfinal_view'),
    path('store_swapcancelconfirm_data/', views.store_swapcancelconfirm_data_view, name='store_swapcancelconfirm_data_view'),
    path('swapcancelconfirm/', views.swapcancelconfirm_view, name='swapcancelconfirm_view'),
    path('store_swapcancel_data/', views.store_swapcancel_data_view, name='store_swapcancel_data_view'),
    path('swapcancel/', views.swapcancel_view, name='swapcancel_view'),
    path('store_countercancelconfirm_data/', views.store_countercancelconfirm_data_view, name='store_countercancelconfirm_data_view'),
    path('countercancelconfirm/', views.countercancelconfirm_view, name='countercancelconfirm_view'),
    path('store_countercancel_data/', views.store_countercancel_data_view, name='store_countercancel_data_view'),
    path('countercancel/', views.countercancel_view, name='countercancel_view'),
    path('swapnoneavail/', views.swapnoneavail_view, name='swapnoneavail_view'),
    path('subswap_dashboard/', views.subswap_dashboard_view, name='subswap_dashboard_view'),
    path('subswap_details/', views.subswap_details_view, name='subswap_details'),
    path('subswap_admin_change/', views.subswap_admin_change_view, name='subswap_admin_change_view'),
    path('subswap_admin_update/', views.subswap_admin_update_view, name='subswap_admin_update_view'),
    path('statistics/', views.statistics_view, name='statistics_view'),
    path('players/', views.players_view, name='players_view'),
    path('profile/', views.profile_view, name='profile_view'),
    path('player_update/', views.player_update_view, name='player_update_view'),
    path('rounds_leaderboard/', views.rounds_leaderboard_view, name='rounds_leaderboard_view'),
    path('password_change/', CustomPasswordChangeView.as_view(), name='password_change'),  
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='GRPR/password_change_done.html'), name='password_change_done'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='GRPR/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='GRPR/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='GRPR/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='GRPR/password_reset_complete.html'), name='password_reset_complete'),
    path('admin_page/', views.admin_view, name='admin_page'),
    path('admin/toggle-gascup/', views.toggle_gascup_view, name='toggle_gascup_view'),
    path('email_test/', views.email_test_view, name='email_test_view'),
    path('automated_msg_admin/', views.automated_msg_admin_view, name='automated_msg_admin_view'),
    path('automated_msg_confirm/', views.automated_msg_confirm_view, name='automated_msg_confirm_view'),
    path('automated_msg_sent/', views.automated_msg_sent_view, name='automated_msg_sent_view'),
    path('text_test/', views.text_test_view, name='text_test_view'),
    path('error_message/<str:error_msg>/', views.error_message_view, name='error_message_view'),
    path('sms/reply/', sms_reply, name='sms_reply'),


    ### Games
    path('games/', views.games_view, name='games_view'),
    path('games_choice/', views.games_choice_view, name='games_choice_view'),

    ### New Game Creation workflow
    path("games/new/date/", views.game_setup_date_view, name="game_setup_date"),
    path("games/setup/course/", views.game_setup_course_view, name="game_setup_course"),
    path("games/setup/players/", views.game_setup_players_view, name="game_setup_players"),
    path("GRPR/games/setup/groups/", views.game_setup_groups_view, name="game_setup_groups"),
    path("GRPR/games/setup/assign/", views.games_view, name="game_setup_assign"),


    ### Skins Game
    path('skins/', views.skins_view, name='skins_view'),
    path('skins/choose/', views.skins_choose_players_view, name='skins_choose_players_view'),
    path('skins/remove_player/', views.skins_remove_player_view, name='skins_remove_player_view'),
    path('skins/choose_replacement_player/', views.skins_choose_replacement_player_view, name='skins_choose_replacement_player_view'),
    path('skins/add_player/', views.skins_add_player_view, name='skins_add_player_view'),
    path('skins/config/', views.skins_config_view, name='skins_config_view'),
    path('skins/undo_game_creation/', views.skins_undo_game_creation, name='skins_undo_game_creation'),
    path('skins/config/confirm/', views.skins_config_confirm_view, name='skins_config_confirm_view'),

    path('skins_admin/', views.skins_admin_view, name='skins_admin_view'),
    path('skins_game_close/', views.skins_game_close_view, name='skins_game_close_view'),
    path('skins/delete_menu/', views.skins_delete_game_menu_view, name='skins_delete_game_menu_view'),
    path('skins/delete_game/', views.skins_delete_game_view, name='skins_delete_game_view'),

    # deprecated section?
    path('skins/new/', views.skins_new_game_view, name='skins_new_game_view'),
    path('skins_invite_view/', views.skins_invite_view, name='skins_invite_view'),
    path('skins/invite/', views.skins_invite_status_view, name='skins_invite_status_view'),
    path('skins/accept_decline/', views.skins_accept_decline_view, name='skins_accept_decline_view'),
    path('skins/tees/', views.skins_choose_tees_view, name='skins_choose_tees_view'),
    # deprecated section end

    path('skins/initiate_scorecard/', views.skins_initiate_scorecard_meta_view, name='skins_initiate_scorecard_meta_view'),
    path('skins/leaderboard/', views.skins_leaderboard_view, name='skins_leaderboard_view'),
    path('skins_close/', views.skins_close_view, name='skins_close_view'),
    path('skins_closed_games/', views.skins_closed_games_view, name='skins_closed_games_view'),
    path('skins_reopen_game/', views.skins_reopen_game_view, name='skins_reopen_game_view'),

    ### Forty Game
    path('forty/', views.forty_view, name='forty_view'),
    path('forty_config/', views.forty_config_view, name='forty_config_view'),
    path('forty_config_confirm/', views.forty_config_confirm_view, name='forty_config_confirm_view'),
    path('forty_game_creation/', views.forty_game_creation_view, name='forty_game_creation_view'),
    path('forty_choose_score/', views.forty_choose_score_view, name='forty_choose_score_view'),
    path('forty_confirm_score/', views.forty_confirm_score_view, name='forty_confirm_score_view'),
    path('forty_input_scores/', views.forty_input_scores_view, name='forty_input_scores_view'),

    ### Gas Cup
    path("gascup/team_assign/", views.gascup_team_assign_view, name="gascup_team_assign_view"),
    path("gascup/teams/", views.gascup_team_assign_view, name="gascup_team_assign_view"),

    ### scorecard work
    path('scorecard/', views.scorecard_view, name='scorecard_view'),
    path('hole_select/', views.hole_select_view, name='hole_select_view'),
    path('hole_score_data/', views.hole_score_data_view, name='hole_score_data_view'),
    path('hole_score/', views.hole_score_view, name='hole_score_view'),
    path('hole_input_score/', views.hole_input_score_view, name='hole_input_score_view'),
    path('hole_display/', views.hole_display_view, name='hole_display_view'),



    
]
