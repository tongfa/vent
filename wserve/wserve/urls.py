from django.conf.urls import patterns, include, url
from wserve import views
# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^$', views.index, name='index'),
    url(r'^audio.html$', views.audio, name='audio'),
    url(r'^lpoll$', views.longcall, name='longcall')
    # Examples:
    # url(r'^$', 'wserve.views.home', name='home'),
    # url(r'^wserve/', include('wserve.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)

from django.contrib.staticfiles.urls import staticfiles_urlpatterns
print staticfiles_urlpatterns()
urlpatterns += staticfiles_urlpatterns()
