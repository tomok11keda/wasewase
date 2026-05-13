from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "category", "created_at")
    list_filter = ("category", "created_at")
    search_fields = ("name", "description", "category")

    # image_url / description も編集対象として使えるよう、デフォルトフォームで表示
    fields = ("name", "price", "description", "category", "image_url", "created_at")

