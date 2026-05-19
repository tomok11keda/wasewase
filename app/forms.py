from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .constants import FACULTY_CHOICES
from .models import (
    Comment,
    CourseThread,
    Product,
    Review,
    ThreadPost,
    TimelinePost,
    UserProfile,
)

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="メールアドレス",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "example@waseda.jp",
                "autofocus": True,
                "autocomplete": "email",
            }
        ),
    )

    error_messages = {
        "invalid_login": "メールアドレスまたはパスワードが正しくありません。",
        "inactive": "このアカウントは無効です。",
    }

    def clean_username(self):
        return (self.cleaned_data.get("username") or "").strip().lower()


class SignUpForm(UserCreationForm):
    faculty = forms.ChoiceField(
        label="学部",
        choices=[("", "学部を選択")] + list(FACULTY_CHOICES),
        required=True,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget = forms.EmailInput(
            attrs={
                "placeholder": "example@waseda.jp",
                "autocomplete": "email",
            }
        )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("このメールアドレスはすでに登録されています。")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("faculty",)
        labels = {"faculty": "学部（認証バッジ）"}


class ProductExhibitForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name",
            "price",
            "description",
            "faculty",
            "course_name",
            "professor_name",
            "image",
        )
        labels = {
            "name": "商品名",
            "price": "値段",
            "description": "説明",
            "faculty": "対象の学部",
            "course_name": "授業名",
            "professor_name": "教授名",
            "image": "写真",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "例：線形代数の教科書"}),
            "price": forms.NumberInput(attrs={"placeholder": "1000", "min": 0}),
            "description": forms.Textarea(
                attrs={"placeholder": "商品の状態や取引方法など", "rows": 5}
            ),
            "course_name": forms.TextInput(
                attrs={"placeholder": "例：線形代数Ⅰ"}
            ),
            "professor_name": forms.TextInput(
                attrs={"placeholder": "例：山田太郎"}
            ),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].choices = [("", "学部を選択")] + list(FACULTY_CHOICES)
        self.fields["faculty"].required = True

    def save(self, commit=True):
        product = super().save(commit=False)
        product.category = "未分類"
        if commit:
            product.save()
        return product


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "comment")
        labels = {
            "rating": "評価",
            "comment": "コメント（任意）",
        }
        widgets = {
            "rating": forms.RadioSelect,
            "comment": forms.Textarea(
                attrs={"placeholder": "短いコメント...", "rows": 2, "maxlength": 200}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].choices = [
            (Review.Rating.BAD, "悪い ★1"),
            (Review.Rating.NORMAL, "普通 ★2"),
            (Review.Rating.GOOD, "良い ★3"),
        ]


class TimelinePostForm(forms.ModelForm):
    class Meta:
        model = TimelinePost
        fields = ("body", "course_name", "professor_name", "faculty")
        labels = {
            "body": "つぶやき",
            "course_name": "授業名タグ",
            "professor_name": "教授名（任意）",
            "faculty": "対象の学部",
        }
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "placeholder": "試験の範囲、質問、情報共有など（280字まで）",
                    "rows": 3,
                    "maxlength": 280,
                }
            ),
            "course_name": forms.TextInput(attrs={"placeholder": "例：線形代数Ⅰ"}),
            "professor_name": forms.TextInput(
                attrs={"placeholder": "教授の名前（任意） 例：山田太郎"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].choices = [("", "自分の登録学部を使う")] + list(
            FACULTY_CHOICES
        )
        self.fields["faculty"].required = False


class CourseThreadForm(forms.ModelForm):
    class Meta:
        model = CourseThread
        fields = ("course_name", "professor_name", "faculty", "description")
        labels = {
            "course_name": "授業名",
            "professor_name": "教授名",
            "faculty": "学部",
            "description": "スレッドの説明",
        }
        widgets = {
            "course_name": forms.TextInput(attrs={"placeholder": "例：マクロ経済学"}),
            "professor_name": forms.TextInput(attrs={"placeholder": "例：佐藤教授"}),
            "description": forms.TextInput(
                attrs={"placeholder": "試験範囲・持ち物など（任意）"}
            ),
        }


class ThreadPostForm(forms.ModelForm):
    class Meta:
        model = ThreadPost
        fields = ("body",)
        labels = {"body": "投稿"}
        widgets = {
            "body": forms.Textarea(
                attrs={"placeholder": "質問や情報を共有...", "rows": 4}
            ),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        labels = {"body": "コメント"}
        widgets = {
            "body": forms.Textarea(
                attrs={"placeholder": "コメントを入力...", "rows": 3}
            ),
        }


class TimelineCommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        labels = {"body": "コメント"}
        widgets = {
            "body": forms.TextInput(attrs={"placeholder": "コメントを入力..."})
        }
