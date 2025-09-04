from django.shortcuts import render

def home(request):
    return render(request, "public/home.html")

def about(request):
    return render(request, "public/about.html")

def privacy(request):
    return render(request, "public/privacy.html")

def contact(request):
    return render(request, "public/contact.html")
