from django.urls import path
from .views import CustomLoginView, DashboardView, twitter_feed, TwitterProfileView

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="custom_login"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("api/", twitter_feed, name="twitter_feed"),
    path("profile/", TwitterProfileView.as_view(), name="profile")
    

]