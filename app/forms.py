from django import forms
# from django.contrib.auth.forms import UserCreationForm # UserCreationFormは使用しない
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
    CustomUser, # CustomUserをインポート
)

# User = get_user_model() # settings.AUTH_USER_MODELがCustomUserを指すようになる


class SignUpForm(forms.ModelForm): # forms.ModelFormを継承
    password = forms.CharField(widget=forms.PasswordInput, label="パスワード")
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="パスワード（確認）")
    faculty = forms.ChoiceField(
        label="学部",
        choices=[("", "学部を選択")] + list(FACULTY_CHOICES),
        required=True,
    )


    class Meta:
        model = CustomUser # CustomUserモデルを使用
        # Meta.fieldsには、モデル(CustomUser)に存在する基本フィールドのみを指定します。
        # パスワードは下で手動定義(forms.CharField)しているため、
        # ここに含めなくても(あるいは含めても)クラス変数の定義が優先されて表示されます。
        fields = ("email", "username")
        labels = {
            "email": "メールアドレス",
            "username": "ユーザー名 (任意)",
        }

    # 表示順序を制御したい場合は field_order を使用します
    field_order = ["email", "username", "faculty", "password", "password_confirm"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # メールアドレスを必須にする場合
        self.fields["email"].required = True
        self.fields["username"].required = False # ユーザー名を任意にする

    def clean_password_confirm(self):
        password = self.cleaned_data.get("password")
        password_confirm = self.cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("パスワードが一致しません。")
        return password_confirm

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
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
            "body": forms.Textarea(
                attrs={"placeholder": "コメントを入力...", "rows": 1}
            )
        }
