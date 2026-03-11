from django.urls import path
from . import views

app_name = 'assessment'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('levels/', views.LevelListView.as_view(), name='levels'),
    path('skills/', views.SkillListView.as_view(), name='skills'),
    path('question-types/', views.QuestionTypeListView.as_view(), name='question-types'),
    path('topics/', views.TopicListView.as_view(), name='topics'),
    path('questions/', views.QuestionListView.as_view(), name='questions'),
    path('questions/<str:question_id>/', views.QuestionDetailView.as_view(), name='question-detail'),
    path('session/start/', views.StartSessionView.as_view(), name='start-session'),
    path('session/<str:session_id>/next/', views.NextQuestionView.as_view(), name='next-question'),
    path('session/<str:session_id>/answer/', views.SubmitAnswerView.as_view(), name='submit-answer'),
    path('session/<str:session_id>/results/', views.SessionResultsView.as_view(), name='session-results'),
    path('tts/', views.TTSView.as_view(), name='tts'),
]
