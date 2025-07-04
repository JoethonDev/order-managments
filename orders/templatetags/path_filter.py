from django import template

register = template.Library()

@register.filter
def extract_path(path):
    path  = path.split("/")
    
    return "/" + "/".join(path[2:])