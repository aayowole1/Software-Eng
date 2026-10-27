# Developer README
This README was developed with the help of gpt-5.6-luna via VS Code's Copilot interface.

## How to Add a New Module
1) Have Django create the module automatically
```bash
docker compose exec web python manage.py startapp [module]
```

2) Register the module by adding `[module].apps.[ModuleConfig]` `orgflow_project/settings.py`; e.g.,
```python
INSTALLED_APPS = [
    # existing apps
    ...

    # new app
    # assume module to add is tasks/
    "tasks.apps.TasksConfig",
]
```

3) Add models, if needed in `[module]/models.py`. Once done, create and apply the migrations.
```python
from django.db import models

class Module(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
```

```bash
# creating and applying migrations
docker compose exec web python manage.py makemigrations tasks
docker compose exec web python manage.py migrate
```

4) Add views and URLs
```python
# create `[module]/urls.py`
from django.urls import path

from . import views

app_name = "module"

url_patterns = [
    path("", views.task_list, name="list"),
]
```

```python
# add a view in `[module]/views.py`
from django.shortcuts import render

from .models import Module


def module_list(request):
    module = Module.objects.all()
    return render(request, "module/module_list.html", {"module": module})
```

```python
# include the app URLs in `orgflow_project/urls.py`
# available at `http://localhost:8000/[module]/`
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    # existing paths
    ...
    # path to add
    path("module/", include("module.urls")),
]
```

5) Create `[module]/templates/[module]/[sub_module].html`

6) Register the model in the admin
```python
# in `[module]/admin.py`
from django.contrib import admin

from .models import Module


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "completed", "created_at")
    list_filter = ("completed",)
    search_fields = ("title", "description")
```

7) Check the project and run tests
```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py test [module]
```
