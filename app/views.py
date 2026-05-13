from django.shortcuts import render

from .models import Product


def index(request):
    categories = [
        {"label": "政治経済学部", "icon": "📚"},
        {"label": "法学部", "icon": "👓"},
        {"label": "商学部", "icon": "💴"},
        {"label": "教育学部", "icon": "🏫"},
        {"label": "文学部", "icon": "📖"},
        {"label": "文化構想学部", "icon": "⌛"},
    ]

    # top.html は product.name / product.price / product.image_url を参照
    products = Product.objects.all()

    return render(
        request,
        "top.html",
        {"categories": categories, "products": products},
    )
 
